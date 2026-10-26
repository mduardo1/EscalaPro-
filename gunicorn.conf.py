"""Linux; confiança de proxy é aplicada no middleware da aplicação."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
worker_class = "gthread"
workers = 1
threads = 2
timeout = 30
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
access_log_format = "%(t)s %(m)s %(U)s %(s)s %(L)s"
forwarded_allow_ips = ""
