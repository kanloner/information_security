# Fix for CVE-2021-25646: build a Druid 0.20.1 image.
#
# The official apache/druid:0.20.1 image uses a distroless base that cannot run
# the nano-quickstart launcher (no bash / perl), so this image keeps the vulhub
# 0.20.0 base - which provides bash, perl, supervise and an embedded ZooKeeper -
# and replaces the vulnerable 0.20.0 jars with the fixed 0.20.1 ones.
FROM vulhub/apache-druid:0.20.0

# Delete the vulnerable jars first. The wildcard covers the core libs and the
# extension jars; "2>/dev/null || true" keeps the build alive when one of the
# two patterns matches nothing, because a failing RUN would abort the layer.
RUN rm -f /opt/druid/lib/*-0.20.0.jar /opt/druid/extensions/*/*-0.20.0.jar 2>/dev/null || true

# Multi-stage copy: take the fixed /opt/druid tree out of the official 0.20.1
# image and drop it into this one. No base-image change, so bash, perl,
# supervise, the embedded ZooKeeper and the port layout all stay exactly as in
# the vulnerable environment - the comparison stays like for like.
COPY --from=apache/druid:0.20.1 /opt/druid/ /opt/druid/

# The launcher that the distroless 0.20.1 image could not run is still here,
# now executing 0.20.1 classes.
CMD ["/opt/druid/bin/start-nano-quickstart"]
