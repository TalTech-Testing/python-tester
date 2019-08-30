# VERSION 0.0.1
FROM ubuntu:bionic
LABEL Description="New python container"
RUN apt-get update
RUN apt-get install -y tzdata
RUN apt-get install -y software-properties-common

RUN apt-get install -y wget git
RUN apt install -y python3.7

RUN apt-get install -y curl
RUN apt install -y python3-pip
RUN pip3 install pytest pep257 mock pytest-console-scripts
RUN pip3 install -e git+https://gitlab.com/pycqa/flake8@9631dac5#egg=flake8
RUN apt-get install -y rsyslog && rsyslogd
ENV TERM=xterm

# tkinter
RUN apt-get install -y python3-tk

# pillow
RUN pip3 install Pillow

# networkX
RUN pip3 install networkx

RUN pip3 install requests
# RUN pip3 install git+git://github.com/okken/pytest-requests.git@107ff7b8ed556d92294728a669183e9f640139e5

#RUN mkdir /deps
ADD . /py_tester

# install package
RUN cd /py_tester && python3.7 -m pip install .

CMD /bin/bash -c "cd /py_tester && timeout 100 python3.7 pytester.py < /host/input.json > /host/output.json"