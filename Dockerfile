FROM nikolaik/python-nodejs:python3.6-nodejs10-stretch


RUN apt-get update; apt-get -y install unzip apt-transport-https \
                                             ca-certificates \
                                             curl \
                                             gnupg2 \
                                             software-properties-common

RUN curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -
RUN add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/debian \
   $(lsb_release -cs) \
   stable"

RUN apt-get update; apt-get -y install docker-ce

RUN pip install chalice==1.12.0 awscli
RUN npm install -g serverless@1.32.0

RUN mkdir /terraform
WORKDIR /terraform

RUN wget https://releases.hashicorp.com/terraform/0.11.8/terraform_0.11.8_linux_amd64.zip
RUN unzip terraform_0.11.8_linux_amd64.zip
RUN cp terraform /usr/local/bin

VOLUME /otm
WORKDIR /otm

