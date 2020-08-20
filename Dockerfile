# VERSION 0.0.1
FROM ubuntu:bionic
LABEL Description="New python container"
ENV TERM=xterm

RUN apt-get update
RUN apt-get install -y tzdata software-properties-common wget git python3-dev python3.7 libpython3.7-dev curl python3-pip rsyslog rsyslogd python3-tk

RUN python3.7 -m pip install --default-timeout=100 pytest pep257 mock pytest-console-scripts flake8 Pillow networkx requests numpy sympy matplotlib torchvision tensorflow pandas freezegun
RUN python3.7 -m pip install --default-timeout=100 torch==1.2.0+cpu torchvision==0.4.0+cpu -f https://download.pytorch.org/whl/torch_stable.html
RUN python3.7 -m pip install --default-timeout=100 --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

ADD . /py_tester
RUN cd /py_tester && python3.7 -m pip install .

CMD /bin/bash -c "cd /py_tester && timeout 100 python3.7 pytester.py < /host/input.json > /host/output.json"
