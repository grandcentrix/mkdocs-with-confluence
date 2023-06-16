# mkdocs-with-confluence

MkDocs plugin that converts markdown pages into confluence markup
and export it to the Confluence page

## How to use

To enable plugin, you need to set the `MKDOCS_TO_CONFLUENCE` environment variable.

```bash
export MKDOCS_TO_CONFLUENCE=1
```

By default, the dry-run mode is turned off. If you want to enable it, you can use the config file, or the `MKDOCS_TO_CONFLUENCE_DRY_RUN` environment variable

```bash
export MKDOCS_TO_CONFLUENCE_DRY_RUN=1
```

## Setup

Install the plugin using pip:

`pip install https://github.com/grandcentrix/mkdocs-with-confluence/releases/download/v0.4.2/mkdocs_with_confluence-0.4.2.tar.gz`

Activate the plugin in `mkdocs.yml`:

```yaml
plugins:
  - search
  - mkdocs-with-confluence
```

More information about plugins in the [MkDocs documentation: mkdocs-plugins](https://www.mkdocs.org/user-guide/plugins/).

## Usage

Use following config and adjust it according to your needs:

```yaml
  - mkdocs-with-confluence:
        host_url: https://<YOUR_CONFLUENCE_DOMAIN>/wiki
        space: <YOUR_SPACE>
        parent_page_name: <YOUR_ROOT_PARENT_PAGE>
        username: <YOUR_USERNAME_TO_CONFLUENCE> # MKDOCS_TO_CONFLUENCE_USER env var can be used
        password: <YOUR_PASSWORD_TO_CONFLUENCE> # MKDOCS_TO_CONFLUENCE_PASSWORD env var can be used
        dryrun: true # MKDOCS_TO_CONFLUENCE_DRY_RUN env var can be used
        header_message: <A_MESSAGE_THAT_WILL_BE_ADDED_TO_EVERY_PAGE>
        upstream_url: <URL_OF_YOUR_MKDOCS_INSTANCE>
        header_warning: "‼️ This page is created automatically, all you changes will be overwritten during the next MKDocs deployment. Do not edit a page here ‼️"
        set_homepage: true
        cleanup: true # MKDOCS_TO_CONFLUENCE_CLEANUP env var can be used

```

## Config description

```yaml
host_url: An URL of yout confluence instance
space: A confluence space that you'd like to sync mkdocs pages to
paren_page_name: A name of a page that should  be a parent page for other pages synced from mkdocs. If not set, mkdocs will be synced directrly to the space
username: Atlassian username
password: Atlassian password (or an access token)
dryrun: If set to `true`, changes won't be applied
header_message: A message to be added to each confluence page
upstream_url: An url of the mkdocs instance, to be added to each confluence page
header_warning: By default it's a warning that pages should not be edited in confluence directrly. You can set whatever you'd like. It could be a `header_message` but I've decided to split them, so you can keep a warning while givin a custom message.
set_homepage: If set to `true`, the page with a path = "/" will be set as the space homepage
cleanup: If set to `true`, pages that are gone from mkdoc will be removed from confluence as well.
```

## Requirements

- md2cf
- mimetypes
- mistune
