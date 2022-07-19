FROM node:18-alpine3.15
WORKDIR /code
RUN npm install -g npm@8.14.0
ENV PATH="/code/node_modules/.bin:${PATH}"
COPY . /code
