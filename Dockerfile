FROM python:3.8-alpine

WORKDIR /app

RUN pip install pipenv

ADD Pipfile /app/
ADD Pipfile.lock /app/

RUN pipenv sync

ADD riddle_bot.py /app/

CMD pipenv run main
