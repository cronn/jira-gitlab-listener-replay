Setup
-----

```
# virtualenv -p python3 virtualenv
# source virtualenv/bin/activate
# pip install --upgrade pip
# pip install -r requirements.txt
# cp config.py.sample config.py
# vi config.py
```

Usage
-----

Example:

```
./replay.py --dry-run \
            --repo-dir /path/to/git/checkout \
            --repo-path='path/to/repo' \
            --start-commit=abcdef \
            --end-commit=fedcba \
            --project-id 42
```
