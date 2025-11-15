# Laboratório Hadoop/Spark

Disciplina: FGA0244 - Programação para Sistemas Paralelos e Distribuídos
Turma: 02
Semestre: 2025.2

## Integrantes 

| Nome | Matrícula |
|------|-----------|
| Felipe Amorim de Araújo | 221022275 |
| Julio Roberto da Silva Neto | 221022041 |
| Pablo Serra Carvalho | 221008679 |
| Raquel Ferreira Andrade | 211062437 |

## 1. Introdução

No presente laboratório, exploramos o uso de frameworks de processamento distribuído, especificamente Hadoop e Spark, para analisar grandes volumes de dados. O objetivo é realizar experimentos práticos que demonstrem as capacidades desses frameworks em termos de desempenho, escalabilidade e facilidade de uso, além de servir de apoio para o aprendizado dos conceitos teóricos abordados na disciplina.

O relatório está estruturado da seguinte forma: na Seção 2, detalhamos o experimento realizado com Hadoop, incluindo a configuração do ambiente, testes de comportamento do framework e testes de tolerância a falhas e performance. Na Seção 3, apresentamos o experimento com Spark, incluindo o teste com coleta de palavras de alguma rede social e criação de um gráfico de nuvens. Finalmente, na Seção 4, discutimos as conclusões obtidas a partir dos experimentos realizados e os comentários e contribuições de cada integrante do grupo.

## 2. Experimento com Hadoop

### 2.1 Arquitetura do Cluster Hadoop

A configuração do ambiente Hadoop foi realizada por meio de contêineres Docker, instânciados por meio do Docker Compose. Em primeiro momento foi criado um arquivo Dockerfile para a imagem do Hadoop, instalando todos os pacotes e dependências necessárias, incluindo o OpenJDK e o Hadoop, além de fazer toda a configuração das variáveis de ambiente do Hadoop.

```Dockerfile
FROM alpine:3.6

USER root

# instala pacotes necessarios
RUN apk add --no-cache openssh openssl openjdk8 rsync bash procps nss wget

ENV JAVA_HOME=/usr/lib/jvm/java-1.8-openjdk
ENV PATH=$JAVA_HOME/bin:$PATH

# configurar ssh sem senha
RUN mkdir -p /root/.ssh
RUN ssh-keygen -q -N "" -t dsa -f /etc/ssh/ssh_host_rsa_key
# ...
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
# ...

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

```
Em conjunto ao Dockerfile, também foram criados os arquivos de configuração do Hadoop, o arquivo de slaves e um script de bootstrap para iniciar os serviços do Hadoop:

- **`core-site.xml`**: Define a configuração central do Hadoop, incluindo o endereço do NameNode (`hdfs://hadoop-master:8020`) e o diretório temporário do sistema. Este arquivo é fundamental para que todos os nós do cluster saibam onde está localizado o sistema de arquivos distribuído.

- **`hdfs-site.xml`**: Configura os diretórios de armazenamento do HDFS, especificando os caminhos para os dados (`dfs.datanode.data.dir`) e metadados do NameNode (`dfs.namenode.name.dir`). Também define o fator de replicação dos dados (padrão 3), garantindo redundância e tolerância a falhas.

- **`mapred-site.xml`**: Configura o framework MapReduce para usar o YARN como gerenciador de recursos (`mapreduce.framework.name=yarn`), definindo também o endereço do JobHistory Server para rastreamento de jobs executados.

- **`yarn-site.xml`**: Configura o YARN, definindo o endereço do ResourceManager (`0.0.0.0:8088`), os serviços auxiliares para o MapReduce (`mapreduce_shuffle`), e as configurações de memória e CPU para os containers.

- **`slaves`**: Lista simples contendo os hostnames dos nós DataNode/NodeManager do cluster (`hadoop-slave1` e `hadoop-slave2`). Este arquivo é utilizado pelos scripts de inicialização para identificar quais nós devem executar os serviços de worker.

- **`bootstrap.sh`**: Script de inicialização que inicia o serviço SSH (necessário para comunicação entre nós) e mantém o contêiner em execução contínua. O SSH é configurado sem senha para permitir que o master execute comandos remotamente nos slaves.

Por fim, foi criado o arquivo docker-compose-build.yml para orquestrar a criação dos contêineres do cluster Hadoop, incluindo o master `hadoop-master` e dois nós escravos `hadoop-slave1` e `hadoop-slave2`, os volumes para persistência de dados `hadoop_master_data`, `hadoop_slave1_data` e `hadoop_slave2_data`, e por fim a rede `hadoop-network` com ip base 172.20.0.0 para comunicação entre os contêineres.

Para cada contâiner também foram expostos as portas necessárias para acesso as interfaces web do HDFS NameNode (9870) e do YARN ResourceManager (8088), além da porta 2122 para acesso via SSH.

```yaml
services:
  hadoop-master:
    build:
      # ...
    networks:
      hadoop-network:
        ipv4_address: 172.20.0.10
    volumes:
      - hadoop_master_data:/hadoop-data
      - ./shared:/shared
    ports:
      - "9870:9870"  # HDFS NameNode Web UI
      - "8088:8088"  # YARN ResourceManager Web UI
      - "2122:2122"  # SSH

  hadoop-slave1:
    build:
      # ...
    networks:
      hadoop-network:
        ipv4_address: 172.20.0.11
    volumes:
      - hadoop_slave1_data:/hadoop-data
      - ./shared:/shared
    ports:
      - "2123:2122"  # SSH

  hadoop-slave2:
    build:
      # ...
    networks:
      hadoop-network:
        ipv4_address: 172.20.0.12
    volumes:
      - hadoop_slave2_data:/hadoop-data
      - ./shared:/shared
    ports:
      - "2124:2122"  # SSH

networks:
  hadoop-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

volumes:
  hadoop_master_data:
  hadoop_slave1_data:
  hadoop_slave2_data:

```
Para instanciar o cluster Hadoop, foram detalhados passos no README do diretório `cluster`. O build da imagem já faz todo o processo de instalação e configuração do Hadoop, precisando apenas acessar os contâiners para formatação do NameNode e para iniciar os serviços do HDFS e YARN no container master.

Comando para build e subida do cluster:
```bash
docker-compose -f docker-compose-build.yml up --build -d
```
Listar contêineres em execução:
```bash
docker ps
```
Comando para formatar NameNode:
```bash
docker exec -it hadoop-master bash -c "hdfs namenode -format"
```
Comando para iniciar serviços do HDFS e YARN:
```bash
docker exec -it hadoop-master bash -c "start-dfs.sh && start-yarn.sh"
```

### 2.2 Testes de Comportamento do Framework

## 3. Experimento com Spark

## 4. Conclusão

| Matrícula | Nome | Contribuições | Autoavaliação (0-10) |
|-----------|------|---------------|-----------------------|
| 221022275 | Felipe Amorim de Araújo |  |  |
| 221022041 | Julio Roberto da Silva Neto |  |  |
| 221008679 | Pablo Serra Carvalho |  |  |
| 211062437 | Raquel Ferreira Andrade |  |  |