#!/usr/bin/env python

import requests
import git
import sys
import json
import time
import argparse
import logging
import re

from collections import OrderedDict

try:
    import config
except ImportError as e:
    print("please provide configuration in file 'config.py'. See 'config.py.sample' for an example.")
    sys.exit(-1)

sys.setrecursionlimit(10000)


logging.basicConfig(format='%(asctime)s %(name)4s %(levelname)-5s %(message)s', datefmt='%H:%M:%S', level=logging.DEBUG)

logger = logging.getLogger("main")


evaluated_commits = set()


def recurse_commits(commit, start, jira_session, repo_path, verbose):

    if commit.hexsha in evaluated_commits:
        return

    commit_filter = re.compile(r'.*?([A-Z]+-\d+):.*')
    match = commit_filter.match(commit.summary)
    if match:
        logger.debug('evaluating %s: "%s"' % (commit.hexsha, commit.summary))

        issue_key = match.group(1)

        response = jira_session.get(config.jira_url + '/activity?maxResults=1000&streams=issue-key+IS+%s' % issue_key, auth=(config.jira_basic_auth_username, config.jira_basic_auth_password))

        id = '<id>https://%s/%s/commit/%s' % (config.git_base_url, repo_path, commit.hexsha)
        if id in response.text:
            logger.info("found commit %s in Jira activity stream" % commit.hexsha)
        else:
            logger.info("commit NOT found in Jira activity stream")
            yield commit
    else:
        if verbose:
            logger.debug('skipping commit %s: "%s"' % (commit.hexsha, commit.summary))

    evaluated_commits.add(commit.hexsha)

    if commit.hexsha == start.hexsha:
        logger.debug("reached start commit")
        return

    for parent in commit.parents:
        yield from recurse_commits(parent,
                                   start=start,
                                   jira_session=jira_session,
                                   repo_path=repo_path,
                                   verbose=verbose)


def replay(repo_dir, repo_path, start, end, project_id, dry_run, verbose):
    repo = git.Repo(repo_dir)

    end = repo.commit(end)
    start = repo.commit(start)

    username = config.jira_basic_auth_username
    password = config.jira_basic_auth_password

    jira_session = requests.Session()
    auth_data = {'username': config.jira_username, 'password': config.jira_password}
    jira_session.post(config.jira_url + '/rest/auth/1/session', json=auth_data, auth=(username, password))

    data = OrderedDict()
    data['object_kind'] = 'push'

    commits = [commit for commit in recurse_commits(end, start=start, jira_session=jira_session, repo_path=repo_path, verbose=verbose)]
    if not commits or len(commits) == 0:
        logger.warn("Found no commits")
        return

    last_commit = commits[-1]
    if len(last_commit.parents) >= 1:
        data['before'] = last_commit.parents[0].hexsha
    else:
        data['before'] = '0000000000000000000000000000000000000000'

    data['after'] = commits[0].hexsha
    data['ref'] = 'refs/heads/master'
    data['checkout_sha'] = commits[0].hexsha
    data['repository'] = OrderedDict()
    data['repository']['url'] = 'git@%s:%s.git' % (config.git_base_url, repo_path)
    data['repository']['homepage'] = 'https://%s/%s' % (config.git_base_url, repo_path)
    data['repository']['description'] = ''
    data['repository']['git_http_url'] = 'https://%s/%s.git' % (config.git_base_url, repo_path)
    data['repository']['git_ssh_url'] = 'git@%s:%s.git' % (config.git_base_url, repo_path)

    data['project_id'] = project_id

    data['commits'] = []

    for commit in commits:
        date = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(commit.authored_date))
        logger.info("%20s @%s (%s): %s" % (commit.author, date, commit.hexsha[:7], commit.summary))

        commit_data = OrderedDict()
        commit_data['id'] = commit.hexsha
        commit_data['message'] = commit.message

        if commit.author_tz_offset == -3600:
            offset = '+01:00'
        elif commit.author_tz_offset == -7200:
            offset = '+02:00'
        elif commit.author_tz_offset == 0:
            offset = '+00:00'
        else:
            assert False, "illegal offset: %s" % repr(commit.author_tz_offset)

        commit_data['timestamp'] = (time.strftime('%Y-%m-%dT%H:%M:%S' + offset, time.gmtime(commit.authored_date)))
        commit_data['url'] = data['repository']['homepage'] + '/commit/' + commit.hexsha
        commit_data['author'] = OrderedDict()
        commit_data['author']['name'] = commit.author.name
        commit_data['author']['email'] = commit.author.email

        commit_data['added'] = []
        commit_data['modified'] = []
        commit_data['removed'] = []

        for added in commit.parents[0].diff(commit).iter_change_type('A'):
            commit_data['added'].append(added.b_path)

        for modified in commit.parents[0].diff(commit).iter_change_type('M'):
            commit_data['modified'].append(modified.b_path)

        for deleted in commit.parents[0].diff(commit).iter_change_type('D'):
            commit_data['removed'].append(deleted.a_path)

        data['commits'].append(commit_data)

    data['total_commits_count'] = len(commits)

    if verbose:
        logger.debug(json.dumps(data, indent=4))

    if dry_run:
        logger.info("dry run. not posting")
    else:
        response = jira_session.post(config.jira_gitlab_listener_url, json=data, auth=(username, password))
        logger.info(response)

    jira_session.delete(config.jira_url + '/rest/auth/1/session', auth=(username, password))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GitLab replay')
    parser.add_argument('--dry-run', '-n', action='count', help='read-only dry run without posting to Jira')
    parser.add_argument('--verbose', '-v', action='count', help='be more verbose')
    parser.add_argument('--repo-dir', required=True, help='path to local .git repository')
    parser.add_argument('--repo-path', required=True, help='path to remote git. Example: user.name/my-repo')
    parser.add_argument('--start-commit', required=True, help='commitish of the first commit to process. Example: master~5')
    parser.add_argument('--end-commit', required=True, help='commitish of the last commit to process. Example: master~1')
    parser.add_argument('--project-id', '-p', required=True, type=int, help='project_id of gitlab project. Example: 42')
    args = parser.parse_args()

    replay(repo_dir=args.repo_dir,
           repo_path=args.repo_path,
           start=args.start_commit,
           end=args.end_commit,
           project_id=args.project_id,
           dry_run=args.dry_run,
           verbose=args.verbose)
