FROM bgruening/galaxy-stable

MAINTAINER Ricardo Medda, medda@crs4.it

ENV GALAXY_CONFIG_BRAND Omero Biobank

WORKDIR /galaxy-central

COPY ajax_dynamic_options.conf.yaml /galaxy-central/scripts/tools
COPY ajax_dynamic_options.py /galaxy-central/scripts/tools
COPY README_ajax_dynamic_options.txt /galaxy-central

RUN   echo "# -- Enable Galaxy to manage tools with Ajax Dynamic Options" >> /galaxy-central/config/galaxy.ini.sample
RUN   echo "ajax_dynamic_options_config_file = scripts/tools/ajax_dynamic_options.conf.yaml" >> /galaxy-central/config/galaxy.ini.sample

COPY __init__.py /galaxy-central/lib/galaxy/model
COPY basic.py /galaxy-central/lib/galaxy/tools/parameters

ADD crs4_omero_tools.yml $GALAXY_ROOT/tools.yaml
RUN install-tools $GALAXY_ROOT/tools.yaml

COPY hack_galaxy.sh /galaxy-central

# Mark folders as imported from the host.
VOLUME ["/export/", "/data/", "/var/lib/docker"]

# Expose port 80 (webserver), 21 (FTP server), 8800 (Proxy)
EXPOSE :80
EXPOSE :21
EXPOSE :8800

# Autostart script that is invoked during container start
CMD ["/usr/bin/startup"]


