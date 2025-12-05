FROM crownpipe-dev-base:latest

COPY compose/cronjobs.txt /etc/cron.d/crownpipe
RUN chmod 0644 /etc/cron.d/crownpipe && crontab /etc/cron.d/crownpipe

CMD ["cron", "-f"]
