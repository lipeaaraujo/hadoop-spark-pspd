# Como instanciar os containers do cluster

Este diretório contém os arquivos necessários para criar e executar um cluster Hadoop usando Docker Compose. Siga as instruções abaixo para instanciar os containers do cluster.

## Pré-requisitos

- Docker instalado na sua máquina.
- Docker Compose instalado na sua máquina.

## Passos para instanciar o cluster

1. Navegue até o diretório `cluster` no terminal:

   ```bash
   cd cluster
   ```

2. Construa e suba os containers do cluster usando o Docker Compose:

   ```bash
   docker-compose -f docker-compose-build.yml up --build -d
    ```
    O comando acima irá construir as imagens Docker necessárias e iniciar os containers em segundo plano.

3. Verifique se os containers estão em execução:
    ```bash
    docker ps
    ```
    Você deve ver os containers do Hadoop Master e dos nós escravos listados.

4. Acesse o container do Hadoop Master para interagir com o cluster:
    ```bash
    docker exec -it <id-master> bash
    ```

5. Dentro do container master, caso for a primeira vez que está iniciando o cluster, formate o NameNode do HDFS e inicie o serviço HDFS e YARN:
    ```bash
    hdfs namenode -format
    start-dfs.sh
    start-yarn.sh
    ```
6. Nos slaves, também formate o NameNode:
    ```bash
    docker exec -it <id-slave1> bash
    hdfs namenode -format
    exit
    docker exec -it <id-slave2> bash
    hdfs namenode -format
    exit
    ```

Acesso as interfaces web:
- http://172.20.0.10:9870/dfshealth.html#tab-overview
- http://172.20.0.10:8088/cluster/apps