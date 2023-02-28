FROM python:latest as BUILDER

FROM BUILDER as plugin_builder
WORKDIR /src
COPY . /src
RUN pip install poetry
RUN poetry build 
RUN mkdir /out
RUN mv $(find /src/dist -maxdepth 1 -mindepth 1 -name '*tar.gz') /out/mkdocs_with_confluence.tar.gz

FROM BUILDER as common_builder
ARG MKDOCS_TO_CONFLUENCE_PASSWORD
ENV MKDOCS_TO_CONFLUENCE=true
ENV MKDOCS_TO_CONFLUENCE_PASSWORD=$MKDOCS_TO_CONFLUENCE_PASSWORD
RUN pip install mkdocs mkdocs-material
WORKDIR /src
COPY ./example /src
COPY --from=plugin_builder /out/mkdocs_with_confluence.tar.gz /tmp/
RUN pip install /tmp/mkdocs_with_confluence.tar.gz
ENTRYPOINT ["mkdocs"]
CMD ["serve", "-a", "0.0.0.0:8000"]

