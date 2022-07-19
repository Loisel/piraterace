FROM node:18-alpine3.15
WORKDIR /code
RUN npm install -g npm@8.14.0
RUN npm install -g @ionic/cli
RUN npm install -g @ionic/lab
COPY . /code
RUN npm install package.json
