from python:3.7-slim
workdir /root
run apt-get update &&apt-get install git -y &&git clone https://github.com/Karunamon/pixlbot&&pip3 install -r /root/pixlbot/requirements.txt --no-cache-dir
expose 8000
workdir /root/pixlbot
entrypoint /usr/local/bin/python3 /root/pixlbot/main.py
