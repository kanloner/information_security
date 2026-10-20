# Fix for CVE-2021-25646: build a Druid 0.20.1 image.
#
# The official apache/druid:0.20.1 image uses a distroless base that cannot run
# the nano-quickstart launcher (no bash / perl), so this image keeps the vulhub
# 0.20.0 base - which provides bash, perl, supervise and an embedded ZooKeeper -
# and replaces the vulnerable 0.20.0 jars with the fixed 0.20.1 ones.
FROM vulhub/apache-druid:0.20.0

RUN rm -f /opt/druid/lib/*-0.20.0.jar /opt/druid/extensions/*/*-0.20.0.jar 2>/dev/null || true
COPY --from=apache/druid:0.20.1 /opt/druid/ /opt/druid/

CMD ["/opt/druid/bin/start-nano-quickstart"]
