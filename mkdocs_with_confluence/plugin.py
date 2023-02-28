import os
import hashlib
import sys
import glob
import re
import tempfile
import shutil
import requests
import mimetypes
import mistune
import contextlib
import time
import logging
logger = logging.getLogger('mkdocs')

from time import sleep
from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin
from md2cf.confluence_renderer import ConfluenceRenderer
from os import environ
from pathlib import Path

ENABLE_ENV_VAR = "MKDOCS_TO_CONFLUENCE"
DRY_RUN_ENV_VAR = "MKDOCS_TO_CONFLUENCE_DRY_RUN"

TEMPLATE_BODY = "<p> TEMPLATE </p>"
HEADER_WARNING = "‼️ This page is created automatically, all you changes will be overwritten during the next MKDocs deployment. Do not edit a page here ‼️"
SECTION_PAGE_CONTENT =  "<p> It's just a Section Page </p>"

# -- I don't know why it's here
@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = DummyFile()
    yield
    sys.stdout = save_stdout

# -- I don't know why it's here
class DummyFile(object):
    def write(self, x):
        pass


class MkdocsWithConfluence(BasePlugin):
    config_scheme = (
        ("host_url", config_options.Type(str, default=None)),
        ("space", config_options.Type(str, default=None)),
        ("parent_page_name", config_options.Type(str, default=None)),
        ("username", config_options.Type(str, default=environ.get("MKDOCS_TO_CONFLUENCE_USER", None))),
        ("password", config_options.Type(str, default=environ.get("MKDOCS_TO_CONFLUENCE_PASSWORD", None))),
        ("dryrun", config_options.Type(bool, default=False)),
        ("header_message", config_options.Type(str, default=None)),
        ("upstream_url", config_options.Type(str, default=None)),
        ("header_warning", config_options.Type(str, default=HEADER_WARNING)),
        ("set_homepage", config_options.Type(bool, default=False)),
    )

    def __init__(self):
        self.enabled = False
        self.confluence_renderer = ConfluenceRenderer(use_xhtml=True)
        self.confluence_mistune = mistune.Markdown(renderer=self.confluence_renderer)
        self.simple_log = False
        self.flen = 1
        self.session = requests.Session()
        self.page_attachments = {}
        self.repo_url = None
        self.header_message = None
        self.upstream_url = None


    def on_config(self, config):
        # ------------------------------------------------------
        # -- Enable the plugin by setting environment variable
        # ------------------------------------------------------
        if os.environ.get(ENABLE_ENV_VAR):
            logger.info("MKDocs with Confluence is enabled")
            self.enabled = True
        else:
            logger.info(
                f"MKDocs with Confluence is disabled, set the {ENABLE_ENV_VAR} to enable the plugin"
            )
        # ------------------------------------------------------
        # -- Set the dry-run mode
        # ------------------------------------------------------
        if self.config["dryrun"]  or os.environ.get(DRY_RUN_ENV_VAR):
            logger.info("dry-run mode is turned on, your changes won't be synced with Confluence")
            self.dryrun = True
        else:
            logger.info("dry-run mode is turned off, your changes will be synced with Confluence")
            self.dryrun = False
        # ------------------------------------------------------
        # -- Set git url to add to a confluence page
        # ------------------------------------------------------
        if config["repo_url"]:
            self.repo_url = config["repo_url"]
            logger.info(f"git url is set to {self.repo_url}")
        # ------------------------------------------------------
        # -- Set a custom header to add to a confluence page
        # ------------------------------------------------------
        if self.config["header_message"]:
            self.header_message = self.config["header_message"]
            logger.info(f"header message is set to {self.header_message}")
        # ------------------------------------------------------
        # -- Set an upstream url to add to a confluence page
        # ------------------------------------------------------
        if self.config["upstream_url"]:
            self.upstream_url = self.config["upstream_url"]
            logger.info(f"upstream url is set to {self.upstream_url}")


    def on_files(self, files, config):
        if self.enabled:
            pages = files.documentation_pages()
            try:
                self.flen = len(pages)
                logger.debug(f"number of Files in directory tree: {self.flen}")
            except 0:
                logger.error("no files found to be synced")

    def on_page_markdown(self, markdown, page, config, files):
        if self.enabled:
            try:
                self.session.auth = (self.config["username"], self.config["password"])
                confluence_page_name = page.url[0:-1]
                #.replace("/", "-")
                if self.config["parent_page_name"] is not None:
                    parent_page = self.config["parent_page_name"]
                else:
                    parent_page = self.config["space"]
                page_name = ""
    
                # TODO: Refactor
                if confluence_page_name.rsplit('/',1)[0]:
                    confluence_page_name = (f"{confluence_page_name.rsplit('/',1)[0]}+{page.title.replace(' ', ' ')}")
                else:
                    confluence_page_name = (f"{page.title.replace(' ', ' ')}")
                    # Create empty pages for sections only
                logger.info("preparing emtpy pages for sections")
                for path in page.url.rsplit("/", 2)[0].split("/"):
                    logger.debug(f"path is {path}")
                    parent_id = self.find_page_id(parent_page)
                    if path:
                        if page_name:
                            page_name = page_name + " " + path
                        else:
                            page_name = path
                        logger.info(f"Will create a page {page_name} under the {parent_page}")
                        self.add_page(page_name, parent_id, SECTION_PAGE_CONTENT)                    
                        parent_page = page_name
                parent_id = self.find_page_id(parent_page)
                confluence_page_name = parent_page + " " + page.title
                new_markdown = markdown
                # -- Adding an upstream url
                if self.upstream_url:
                    new_markdown = f">Original page is here: {self.upstream_url}/{page.url}\n\n" + new_markdown
                # -- Adding a header message
                if self.header_message:
                    new_markdown = f">{self.header_message}\n\n" + new_markdown
                # -- Adding a repo url
                if self.repo_url:
                    new_markdown = f">You can edit documentation here: {self.repo_url}\n\n" + new_markdown
                # -- Adding a header warning                
                new_markdown = f">{self.config['header_warning']}\n\n" + new_markdown
                # -------------------------------------------------
                # -- Sync attachments
                # -------------------------------------------------
                attachments = []
                # -- TODO: support named picture
                md_image_reg = "(?:[!]\[(?P<caption>.*?)\])\((?P<image>.*?)\)(?P<options>\{.*\})?"
                try:
                    for match in re.finditer(md_image_reg, markdown):
                        # -- TODO: I'm sure it can be done better
                        attachment_path = "./docs" + match.group(2)
                        logger.info(f"found image: ./docs{match.group(2)}")
                        images = re.search(md_image_reg, new_markdown)
                        # -- TODO: Options maybe the reason why page is invalid, but I'm not sure about it yet
                        # new_markdown = new_markdown.replace(images.group("options"), "")
                        new_markdown = re.sub(md_image_reg, f"<p><ac:image><ri:attachment ri:filename=\"{os.path.basename(attachment_path)}\"/></ac:image></p>", new_markdown)
                        attachments.append(attachment_path)
                except AttributeError as e:
                    logger.warning(e)
                logger.debug(f"attachments: {attachments}")
                confluence_body = self.confluence_mistune(new_markdown)
                self.add_page(confluence_page_name, parent_id, confluence_body)
                logger.info(f"page url = {page.url}")
                if not page.url and self.config["set_homepage"]:
                    self.set_homepage(confluence_page_name)

                if attachments:
                    logger.debug(f"UPLOADING ATTACHMENTS TO CONFLUENCE FOR {page.title}, DETAILS:")
                    logger.debug(f"FILES: {attachments}")
                for attachment in attachments:
                    logger.debug(f"trying to upload {attachment} to {confluence_page_name}")
                    if self.enabled:
                        try: 
                            self.add_or_update_attachment(confluence_page_name, attachment)
                        except Exception as Argument:
                            logger.warning(Argument)
            except Exception as exp:
                logger.error(exp)
            return markdown

    def on_post_page(self, output, page, config):
        if self.enabled:
            logger.info("The author was uploading images here, maybe there was a reason for that")

    def on_page_content(self, html, page, config, files):
        return html

    def __get_page_url(self, section):
        return re.search("url='(.*)'\\)", section).group(1)[:-1] + ".md"

    def __get_page_name(self, section):
        return os.path.basename(re.search("url='(.*)'\\)", section).group(1)[:-1])

    def __get_section_name(self, section):
        logger.debug(f"SECTION name: {section}")
        return os.path.basename(re.search("url='(.*)'\\/", section).group(1)[:-1])

    def __get_section_title(self, section):
        logger.debug(f"SECTION title: {section}")
        try:
            r = re.search("Section\\(title='(.*)'\\)", section)
            return r.group(1)
        except AttributeError:
            name = self.__get_section_name(section)
            logger.warning(f"Section '{name}' doesn't exist in the mkdocs.yml nav section!")
            return name

    def __get_page_title(self, section):
        try:
            r = re.search("\\s*Page\\(title='(.*)',", section)
            return r.group(1)
        except AttributeError:
            name = self.__get_page_url(section)
            logger.warning(f"Page '{name}' doesn't exist in the mkdocs.yml nav section!")
            return name

    # Adapted from https://stackoverflow.com/a/3431838
    def get_file_sha1(self, file_path):
        hash_sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha1.update(chunk)
        return hash_sha1.hexdigest()

    def add_or_update_attachment(self, page_name, filepath):
        logger.warning(f"Mkdocs With Confluence * {page_name} *ADD/Update ATTACHMENT if required* {filepath}")
        logger.debug(f"Mkdocs With Confluence: Add Attachment: PAGE NAME: {page_name}, FILE: {filepath}")
        page_id = self.find_page_id(page_name)
        if page_id:
            file_hash = self.get_file_sha1(filepath)
            attachment_message = f"MKDocsWithConfluence [v{file_hash}]"
            existing_attachment = self.get_attachment(page_id, filepath)
            if existing_attachment:
                file_hash_regex = re.compile(r"\[v([a-f0-9]{40})]$")
                existing_match = file_hash_regex.search(existing_attachment["version"]["message"])
                if existing_match is not None and existing_match.group(1) == file_hash:
                    logger.debug(f" * Mkdocs With Confluence * {page_name} * Existing attachment skipping * {filepath}")
                else:
                    self.update_attachment(page_id, filepath, existing_attachment, attachment_message)
            else:
                self.create_attachment(page_id, filepath, attachment_message)
        else:
            logger.debug("PAGE DOES NOT EXISTS")

    def get_attachment(self, page_id, filepath):
        name = os.path.basename(filepath)
        logger.debug(f" * Mkdocs With Confluence: Get Attachment: PAGE ID: {page_id}, FILE: {filepath}")

        url = self.config["host_url"] + "/content/" + page_id + "/child/attachment"
        headers = {"X-Atlassian-Token": "no-check"}  # no content-type here!
        logger.debug(f"URL: {url}")

        r = self.session.get(url, headers=headers, params={"filename": name, "expand": "version"})
        r.raise_for_status()
        with nostdout():
            response_json = r.json()
        if response_json["size"]:
            return response_json["results"][0]

    def update_attachment(self, page_id, filepath, existing_attachment, message):
        logger.debug(f" * Mkdocs With Confluence: Update Attachment: PAGE ID: {page_id}, FILE: {filepath}")

        url = self.config["host_url"] + "/content/" + page_id + "/child/attachment/" + existing_attachment["id"] + "/data"
        headers = {"X-Atlassian-Token": "no-check"}  # no content-type here!
        logger.debug(f"URL: {url}")
        filename = os.path.basename(filepath)

        # determine content-type
        content_type, encoding = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "multipart/form-data"
        files = {"file": (filename, open(Path(filepath), "rb"), content_type), "comment": message}

        if not self.dryrun:
            r = self.session.post(url, headers=headers, files=files)
            r.raise_for_status()
            logger.debug(r.json())
            if r.status_code == 200:
                logger.info("OK!")
            else:
                print("ERR!")

    def create_attachment(self, page_id, filepath, message):
        logger.debug(f" * Mkdocs With Confluence: Create Attachment: PAGE ID: {page_id}, FILE: {filepath}")

        url = self.config["host_url"] + "/content/" + page_id + "/child/attachment"
        headers = {"X-Atlassian-Token": "no-check"}  # no content-type here!
        logger.debug(f"URL: {url}")

        filename = os.path.basename(filepath)

        # determine content-type
        content_type, encoding = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "multipart/form-data"
        files = {"file": (filename, open(filepath, "rb"), content_type), "comment": message}
        if not self.dryrun:
            r = self.session.post(url, headers=headers, files=files)
            logger.debug(r.json())
            r.raise_for_status()
            if r.status_code == 200:
                logger.debug("OK!")
            else:
                logger.debug("ERR!")

    def find_page_id(self, page_name):
        logger.info(f"looking for a page id of the page: {page_name}")
        name_confl = page_name.replace(" ", "+")
        url = self.config["host_url"] + "/content?title=" + name_confl + "&spaceKey=" + self.config["space"] + "&expand=history"
        logger.debug(f"URL: {url}")

        r = self.session.get(url)
        r.raise_for_status()
        with nostdout():
            response_json = r.json()
        if response_json["results"]:
            logger.debug(f"response: {response_json}")
            return response_json["results"][0]["id"]
        else:
            logger.warning(f"page {page_name} doens't exist")
            return None

    def add_page(self, page_name, parent_page_id, page_content_in_storage_format):
        logger.info(f"Creating a new page: {page_name} under page with ID: {parent_page_id}")
        if self.enabled:
            if self.find_page_id(page_name):
                self.update_page(page_name, page_content_in_storage_format)
            else:
                logger.info(f"Creating a new page: {page_name} under page with ID: {parent_page_id}")
                url = self.config["host_url"] + "/content/"
                logger.debug(f"URL: {url}")
                headers = {"Content-Type": "application/json"}
                space = self.config["space"]
                data = {
                    "type": "page",
                    "title": page_name,
                    "space": {"key": space},
                    "ancestors": [{"id": parent_page_id}],
                    "body": {"storage": {"value": page_content_in_storage_format, "representation": "storage"}},
                }
                logger.debug(f"DATA: {data}")
                if not self.dryrun:
                    try:
                        r = self.session.post(url, json=data, headers=headers)
                        r.raise_for_status()
                    except Exception as exp:
                        logger.error(exp)
                    if r.status_code == 200:
                        logger.info(f"page created: {page_name}")
                    else:
                        logger.error(f"page can't be created: {page_name}")

    def update_page(self, page_name, page_content_in_storage_format):
        page_id = self.find_page_id(page_name)
        logger.debug(f"updating page {page_name}")
        if page_id:
            page_version = self.find_page_version(page_name)
            page_version = page_version + 1
            url = self.config["host_url"] + "/content/" + page_id
            headers = {"Content-Type": "application/json"}
            space = self.config["space"]
            data = {
                "id": page_id,
                "title": page_name,
                "type": "page",
                "space": {"key": space},
                "body": {"storage": {"value": page_content_in_storage_format, "representation": "storage"}},
                "version": {"number": page_version},
            }

            if not self.dryrun:
                try:
                    r = self.session.put(url, json=data, headers=headers)
                    r.raise_for_status()
                except Exception as exp:
                    logger.error(exp)
                if r.status_code == 200:
                    logger.info(f"page created: {page_name}")
                else:
                    logger.error(f"page can't be created: {page_name}")
        else:
            logger.warning("page {page_name} doesn't exist")

    def find_page_version(self, page_name):
        logger.debug(f"INFO    -   * Mkdocs With Confluence: Find PAGE VERSION, PAGE NAME: {page_name}")
        name_confl = page_name.replace(" ", "+")
        url = self.config["host_url"] + "/content?title=" + name_confl + "&spaceKey=" + self.config["space"] + "&expand=version"
        r = self.session.get(url)
        r.raise_for_status()
        with nostdout():
            response_json = r.json()
        if response_json["results"] is not None:
            logger.debug(f"VERSION: {response_json['results'][0]['version']['number']}")
            return response_json["results"][0]["version"]["number"]
        else:
            logger.debug("PAGE DOES NOT EXISTS")
            return None

    def find_parent_name_of_page(self, name):
        logger.debug(f"INFO    -   * Mkdocs With Confluence: Find PARENT OF PAGE, PAGE NAME: {name}")
        idp = self.find_page_id(name)
        url = self.config["host_url"] + "/content" + idp + "?expand=ancestors"

        r = self.session.get(url)
        r.raise_for_status()
        with nostdout():
            response_json = r.json()
        if response_json:
            logger.debug(f"PARENT NAME: {response_json['ancestors'][-1]['title']}")
            return response_json["ancestors"][-1]["title"]
        else:
            logger.debug("PAGE DOES NOT HAVE PARENT")
            return None

    def wait_until(self, condition, interval=0.1, timeout=1):
        start = time.time()
        while not condition and time.time() - start < timeout:
            time.sleep(interval)
    
    def set_homepage(self, page_name):
        page_id = self.find_page_id(page_name)
        url = self.config["host_url"] + "/space/" + self.config["space"]
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        # data = {"homepage": {"id": page_id}} 
        if not self.dryrun:
            logger.info("getting the space information")
            try:
                r = self.session.get(url, headers=headers)
                r.raise_for_status
                with nostdout():
                    response_json = r.json()
            except Exception as exp:
                logger.warning(r.json())
                logger.error(exp)
            response_json['homepage'] = { "id": page_id }
            try:
                r = self.session.put(url, json=response_json, headers=headers)
                r.raise_for_status()
            except Exception as exp:
                logger.warning(r.json())
                logger.error(exp)
            if r.status_code == 200:
                logger.info(f"A page with this id is now a homepage in the space: {page_id}")
            else:
                logger.error(f"Can't set homepage to: {page_id}")
