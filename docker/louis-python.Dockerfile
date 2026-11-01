# The image for run_code (python, sh) when the code runs files of the project that import its dependencies: the
# sandbox has no network, so they must be in the image. Build it once, then set it in src/config/settings.py:
#   docker build -t louis-python -f docker/louis-python.Dockerfile .
#   "sandbox.languages": {"python": {"image": "louis-python"}, "sh": {"image": "louis-python"}}
FROM python:3.13-alpine
COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-dev.txt && rm /tmp/requirements*.txt
