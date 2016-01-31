Setup
-----

# virtualenv -p python3 virtualenv
# source virtualenv/bin/activate
# pip install --upgrade pip
# pip install -r requirements.txt

Usage
-----

Example:

```
./replay.py --dry-run \
            --repo-dir /path/to/git/checkout \
			--repo-path='hpbx-cc/hpbx-cc-src' \
			--start-commit=4812eb \
			--end-commit=4812eb \
			--project-id 4
```
