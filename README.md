# mkdocs-with-confluence 

MkDocs plugin that converts markdown pages into confluence markup
and export it to the Confluence page

# How to use
To enable plugin, you need to set the `MKDOCS_TO_CONFLUENCE` environment variable.
```BASH
export MKDOCS_TO_CONFLUENCE=1
```
By default the dry-run mode is turned off. If you wan't to enable it, you can use the config file, ot the `MKDOCS_TO_CONFLUENCE_DRY_RUN` environment variable
```BASH
export MKDOCS_TO_CONFLUENCE_DRY_RUN=1
```

## Setup
Install the plugin using pip:

`pip install mkdocs-with-confluence`

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
        host_url: https://<YOUR_CONFLUENCE_DOMAIN>/rest/api/content
        space: <YOUR_SPACE>
        parent_page_name: <YOUR_ROOT_PARENT_PAGE>
        username: <YOUR_USERNAME_TO_CONFLUENCE>
        password: <YOUR_PASSWORD_TO_CONFLUENCE>
        dryrun: true
```

## Parameters:

### Requirements
- md2cf
- mimetypes
- mistune
