WSCORE_THRESHOLD = 0.07
WSCORE_HITS_THRESHOLD = 5
WSS_THRESHOLD = 0.1

LOAD_NREVIEWS = 500
MAX_USER_REVIEWS = 250

SLEEPTIME = 0
DATAFORMAT_VERSION = 4
SUMMARY_PERIOD = 10*60


# grep reviewApiKey in https://2gis.ru/ , see contrib/
REVIEWS_KEY = '6e7e1929-4ea9-4a5d-8c05-d601860389bd'

REDIS_TASK_QUEUE_NAME="af2gis:queue"
REDIS_TRUSTED_LIST="af2gis:last_trusted_list"
REDIS_UNTRUSTED_LIST="af2gis:last_untrusted_list"
REDIS_WORKER_STATUS="af2gis:worker_status"
REDIS_WORKER_STATUS_SET="af2gis:worker_status_set"
REDIS_WORKER_STARTED="af2gis:worker_started"
REDIS_DRAMATIQ_QUEUE="dramatiq:default"

LMDB_MAP_SIZE = 1 << 36
