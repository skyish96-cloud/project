import logging

class Logger:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s : %(filename)s - %(asctime)s\n%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Elasticsearch transport 로그 차단
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)

    def get_logger(self,name):
        return logging.getLogger(name)