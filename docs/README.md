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
A etapa de experimentação deste trabalho focou na avaliação prática da resiliência e tolerância a falhas do cluster Hadoop implementado. Para este fim, foi desenhado um cenário de teste que consiste na execução do job WordCount sobre o HDFS, concomitantemente à injeção programada de falhas nos contêineres de serviço. Todo o processo foi automatizado e orquestrado pelo script cluster/tools/run_fault_tests.py.

O fluxo experimental consistiu nas seguintes etapas:

(i) Preparação do dataset de entrada no HDFS, no diretório `/datasets/wordcount`.

(ii) Submissão da aplicação `WordCount` via `hadoop jar`.

(iii) Monitoramento periódico do progresso do job, com registro de amostras e eventos em formato `.jsonl` no diretório `cluster/shared/reports/`.
(iv) Injeção de falhas (via comandos `docker stop/start`) conforme um cronograma pré-definido por linha de comando.


### Escopo dos Eventos de Falha Avaliados

O cronograma de falhas padrão incluiu:

1.  Interrupção do `hadoop-slave1` após 120 segundos, por um período de 60 segundos.
2.  Interrupção do `hadoop-slave2` após 420 segundos, por um período de 60 segundos.
3.  (Opcional) Interrupção do `hadoop-master` após 840 segundos, por 60 segundos. Este evento requer considerações especiais, discutidas abaixo.

### Resultados Observados

* **Falhas em Nós de Trabalho (Slaves):** A interrupção de `DataNodes`/`NodeManagers` foi tolerada pelo sistema. O job prosseguiu, e o YARN automaticamente re-executou *tasks* perdidas e realocou contêineres nos nós restantes. Observou-se uma degradação no *throughput* durante os períodos de indisponibilidade, resultando em um aumento no tempo total de execução (TTE). Os arquivos de log `.jsonl` permitiram correlacionar com precisão os picos de latência e reexecuções de *tasks* com os intervalos de falha injetados.

* **Falha no Nó Mestre (Master) durante a Execução:** A interrupção do `hadoop-master` resultou em falha catastrófica do job. Os logs de execução (ex: `fault_test_20251115-195241.job.log`) indicaram que a aplicação `WordCount` permaneceu estagnada (ex: `map 0% reduce 0%`) ou falhou devido a erros de comunicação IPC. Isso ocorre pois, neste *setup*, o processo cliente (o `hadoop jar`) é executado dentro do próprio contêiner mestre. Ao interromper o contêiner, o processo cliente é terminado, o job é perdido e o sumário final (`.summary.json`) não é gerado. Mesmo após a reinicialização do mestre, os serviços (ResourceManager/NameNode) não retomaram a aplicação.

* **Falhas na Preparação do Dataset:** Em algumas execuções, o comando de verificação `hdfs dfs -test -d /datasets/wordcount` falhou. As causas identificadas foram: (a) os serviços HDFS/YARN ainda estavam em processo de inicialização; (b) o diretório local de dados (`./shared/wordcount-data`) estava vazio; ou (c) o volume do Docker (`./shared`) não foi montado corretamente.

### Inferências Técnicas

* **Resiliência dos Nós de Trabalho:** A arquitetura demonstra tolerância a falhas em DataNodes e NodeManagers. Isso é atribuído ao fator de replicação do HDFS (garantindo a disponibilidade dos dados) e à capacidade do YARN de gerenciar e realocar *tasks*.
* **Ponto Único de Falha (SPOF):** O NameNode e o ResourceManager permanecem como pontos únicos de falha nesta configuração *singleton*. A falha do nó mestre, que também hospeda o cliente do job, compromete toda a execução.
* **Eficácia da Observabilidade:** Os artefatos gerados (`.job.log` e `.jsonl`) provaram ser suficientes para a observabilidade do sistema. Em `fault_test_20251115-195241.job.log`, foi possível correlacionar o avanço do job (aprox. 32%) com falhas subsequentes nos *reducers* (Shuffle$ShuffleError, Exceeded MAX_FAILED_UNIQUE_FETCHES), que ocorreram imediatamente após a indisponibilidade do contêiner que servia os *outputs* intermediários.

---

### Impacto das falhas programadas

| Evento | Observação | Consequência |
|--------|------------|--------------|
| `stop hadoop-slave1` aos 120 s | Interrupção das *tasks* hospedadas no contêiner. | Reexecução automática dos mapas afetados e queda momentânea para ~15 % de progresso. |
| `stop hadoop-slave2` aos 420 s | Nova perda de dados intermediários em produção. | Série de ShuffleError e reinicialização de reducers; curva de progresso ficou “serrilhada”. |
| (Opcional) `stop hadoop-master` | Teste não concluído com sucesso. | Job abortado porque o cliente hadoop jar reside no master; não há *failover* configurado. |

### Métricas de tempo e custo de recuperação

* Tempo médio para o YARN detectar a queda de um NodeManager: ~10 s (com base nas diferenças `elapsed_s` entre eventos de parada e as primeiras linhas de reexecução).
* Janela de recuperação completa após cada falha de *slave*: 60 – 90 s, contabilizando o tempo para o contêiner voltar, registrar-se no ResourceManager e liberar recursos para novas *tasks*.
* Overhead acumulado: os jobs que normalmente terminam em ~8 min levaram ~15 min com as duas falhas planejadas, representando um acréscimo de ~90 % no TTE.

#### 2.2.1 Preparação dos Textos de Entrada

Os arquivos utilizados nos testes são gerados por dois *scripts* shell disponíveis em cluster/shared/:

1. `download_gutenberg_corpus.sh`: baixa obras públicas do Project Gutenberg.
2. `generate_wordcount_data.sh`: cria textos sintéticos grandes para sobrecarregar o HDFS.

Como ambos requerem utilitários POSIX (`bash`, `wget/curl`, `awk`, `unzip`), recomendamos executá-los dentro do contêiner hadoop-master (ou em qualquer host Linux compatível) seguindo os passos abaixo:

```powershell
cd .\cluster
docker exec -it hadoop-master bash
```

Dentro do *shell* do contêiner:

```bash
cd /shared
chmod +x download_gutenberg_corpus.sh generate_wordcount_data.sh

# 1) Baixar livros do Gutenberg (personalize BOOK_IDS, OVERWRITE ou DATA_DIR se necessário)
BOOK_IDS="11 84 1342 1661" OVERWRITE=0 ./download_gutenberg_corpus.sh

# 2) Gerar lotes sintéticos (ajuste FILES/LINES_PER_FILE para calibrar o volume)
FILES=8 LINES_PER_FILE=2000000 ./generate_wordcount_data.sh

exit
```

---
## 3. Experimento com Spark

O experimento com Apache Spark, foi desenvolvido para atender aos requisitos de processamento de streaming definidos no item B2 do documento de especificação. Conforme implementado no notebook, o sistema de entrada de dados foi substituído por uma fonte em tempo real, utilizando a API de uma rede social. Para isso, um bot do Discord foi configurado para atuar como um produtor Kafka, capturando ativamente as mensagens enviadas por usuários em um canal e publicando-as, em tempo real, no tópico Kafka de entrada (canalinput). Uma aplicação Spark Structured Streaming é então conectada a este tópico, consumindo o fluxo de mensagens à medida que elas chegam. Dentro do Spark, um pipeline de transformação é aplicado: as mensagens de texto são primeiramente segmentadas em palavras individuais (split), distribuídas em linhas distintas e padronizadas (convertidas para maiúsculas). A principal lógica de negócio, a contabilização de palavras (WordCount), é executada de forma contínua sobre esses dados. Para garantir o processamento eficiente e a gestão de dados que podem chegar com atraso, a agregação é feita utilizando janelas de tempo (window). Finalmente, os resultados dessa contabilização (palavra, contagem e janela de tempo) são formatados em JSON e enviados para o tópico Kafka de saída (canaloutput). Embora o pipeline de dados desde a captura no Discord até o processamento no Spark e a saída no Kafka esteja funcional, a etapa final de visualização gráfica com ElasticSearch e Kibana, conforme sugerido nas instruções, não foi implementada, restando os dados processados disponíveis no tópico de saída.

## 4. Conclusão
Neste rela´torio, exploramos na prática as arquiteturas e os casos de uso dos frameworks Apache Hadoop e Apache Spark, fundamentais no ecossistema de Big Data. Os experimentos permitiram contrastar o processamento em lote (batch) do Hadoop com o processamento em streaming do Spark.
No experimento com Hadoop, a configuração do cluster com um nó mestre e dois escravos foi realizada utilizando contêineres Docker, conforme detalhado na arquitetura. Durante os testes de tolerância a falhas , . Uma das principais vantagens foi a robustez do HDFS para grandes volumes de dados. Uma das desvantagens identificadas a complexidade da configuração inicial dos arquivos XML  e o overhead do MapReduce.

O experimento com Spark focou no processamento de streaming , com o objetivo de coletar dados de uma rede social (Discord) e gerar uma saída gráfica.

No experimento com Spark, o foco foi o processamento de streaming em tempo real,com o objetivo de coletar dados de uma rede social . A arquitetura da solução, foi implementada para atender ao requisito de usar uma rede social como fonte de dados (Discord). Foi desenvolvido um bot para o Discord que atua como produtor, capturando mensagens de um canal e enviando-as diretamente para um tópico Kafka (canalinput). Em paralelo, uma aplicação Spark Structured Streaming foi configurada para consumir os dados desse tópico. A lógica do Spark processa o stream, aplica as transformações para contagem de palavras (WordCount) agrupadas em janelas de tempo, e prepara os resultados agregados em formato JSON para um tópico de saída (canaloutput).

Embora a lógica completa deste pipeline de dados esteja implementada no notebook, a execução no ambiente local foi comprometida por desafios de infraestrutura.A etapa final, referente à substituição da saída por um dashboard gráfico com ElasticSearch e Kibana, não foi implementada, restando o pipeline com a saída dos dados processados de volta ao Kafka.

Em suma, o laboratório consolidou os conceitos teóricos da disciplina, demonstrando a força do Hadoop para processamento batch robusto e a velocidade e flexibilidade do Spark para análises em tempo real



| Matrícula | Nome | Contribuições | Autoavaliação (0-10) |
|-----------|------|---------------|-----------------------|
| 221022275 | Felipe Amorim de Araújo |  |  |
| 221022041 | Julio Roberto da Silva Neto |  |  |
| 221008679 | Pablo Serra Carvalho |  |  |
| 211062437 | Raquel Ferreira Andrade |  |  |