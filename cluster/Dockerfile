FROM alpine:3.6

USER root

# instala pacotes necessarios
RUN apk add --no-cache openssh openssl openjdk8 rsync bash procps nss wget

ENV JAVA_HOME=/usr/lib/jvm/java-1.8-openjdk
ENV PATH=$JAVA_HOME/bin:$PATH

# configurar ssh sem senha
RUN mkdir -p /root/.ssh
RUN ssh-keygen -q -N "" -t dsa -f /etc/ssh/ssh_host_rsa_key
RUN ssh-keygen -q -N "" -t rsa -f /etc/ssh/ssh_host_dsa_key
RUN ssh-keygen -q -N "" -t rsa -f /root/.ssh/id_rsa
RUN ssh-keygen -q -N "" -t ecdsa -f /etc/ssh/ssh_host_ecdsa_key
RUN ssh-keygen -q -N "" -t ed25519 -f /etc/ssh/ssh_host_ed25519_key
RUN cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# copia arquivo de configuracao do ssh e seta permissoes para o root
ADD ssh_config /root/.ssh/config
RUN chmod 600 /root/.ssh/config
RUN chown root:root /root/.ssh/config

RUN echo "Port 2122" >> /etc/ssh/sshd_config

RUN passwd -u root

# instalar hadoop
RUN wget -O hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-2.7.4/hadoop-2.7.4.tar.gz && \
	tar -xzf hadoop.tar.gz -C /usr/local/ && rm hadoop.tar.gz

# criar soft link para facilitar referencias futuras
RUN ln -s /usr/local/hadoop-2.7.4/ /usr/local/hadoop

# configurar variaveis de ambiente do hadoop
ENV HADOOP_HOME=/usr/local/hadoop
ENV PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin

ENV HADOOP_PREFIX=$HADOOP_HOME
ENV HADOOP_COMMON_HOME=$HADOOP_HOME
ENV HADOOP_HDFS_HOME=$HADOOP_HOME
ENV HADOOP_MAPRED_HOME=$HADOOP_HOME
ENV HADOOP_YARN_HOME=$HADOOP_HOME
ENV HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
ENV YARN_CONF_DIR=$HADOOP_PREFIX/etc/hadoop

# criar config files padroes
ADD config/* $HADOOP_HOME/etc/hadoop/

# atualizar JAVA_HOME e HADOOP_CONF no hadoop-env.sh
RUN chmod +x $HADOOP_HOME/etc/hadoop/hadoop-env.sh
RUN sed -i "/^export JAVA_HOME/ s:.*:export JAVA_HOME=${JAVA_HOME}\nexport HADOOP_HOME=${HADOOP_HOME}\nexport HADOOP_PREFIX=${HADOOP_PREFIX}:" ${HADOOP_HOME}/etc/hadoop/hadoop-env.sh
RUN sed -i '/^export HADOOP_CONF_DIR/ s:.*:export HADOOP_CONF_DIR=$HADOOP_PREFIX/etc/hadoop/:' $HADOOP_PREFIX/etc/hadoop/hadoop-env.sh

WORKDIR $HADOOP_HOME

ADD bootstrap.sh /etc/bootstrap.sh
RUN chmod +x /etc/bootstrap.sh

CMD [ "/etc/bootstrap.sh", "-d" ]
