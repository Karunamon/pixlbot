FROM nuvandibe/python3-pipenv-alpine:latest
COPY . /app
WORKDIR /app
VOLUME /app/db

RUN pipenv install --system --deploy --ignore-pipfile

CMD python main.py
