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
#from loguru import logger
logger = logging.getLogger('mkdocs')

from time import sleep
from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin
from md2cf.confluence_renderer import ConfluenceRenderer
from os import environ
from pathlib import Path
from atlassian import Confluence

ENABLE_ENV_VAR = "MKDOCS_TO_CONFLUENCE"
DRY_RUN_ENV_VAR = "MKDOCS_TO_CONFLUENCE_DRY_RUN"

TEMPLATE_BODY = "<p> TEMPLATE </p>"
HEADER_WARNING = "‼️ This page is created automatically, all you changes will be overwritten during the next MKDocs deployment. Do not edit a page here ‼️"
SECTION_PAGE_CONTENT =  "<p> It's just a Section Page </p>"
PAGE_LABEL = "synced_from_mkdocs"

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
        ("host_url", config_options.Type(str, default=environ.get("MKDOCS_TO_CONFLUENCE_HOST_URL", None))),
        ("space", config_options.Type(str, default=None)),
        ("parent_page_name", config_options.Type(str, default=None)),
        ("username", config_options.Type(str, default=environ.get("MKDOCS_TO_CONFLUENCE_USER", None))),
        ("password", config_options.Type(str, default=environ.get("MKDOCS_TO_CONFLUENCE_PASSWORD", None))),
        ("dryrun", config_options.Type(bool, default=False)),
        ("header_message", config_options.Type(str, default=None)),
        ("upstream_url", config_options.Type(str, default=None)),
        ("header_warning", config_options.Type(str, default=HEADER_WARNING)),
        ("set_homepage", config_options.Type(bool, default=False)),
        ("cleanup", config_options.Type(bool, default=environ.get("MKDOCS_TO_CONFLUENCE_CLEANUP", False))),
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
        self.confluence = None
        self.pages = []


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
                logger.debug(f"number of files in directory tree: {self.flen}")
            except 0:
                logger.error("no files found to be synced")

    def on_page_markdown(self, markdown, page, config, files):
        if self.enabled:
            try:
                # -------------------------------
                # -- Init the Confluence client
                # -------------------------------
                self.confluence = Confluence(
                    url=self.config["host_url"],
                    username=self.config["username"],
                    password=self.config["password"])
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
                logger.info("preparing section pages")
                # -----------------------------------------
                # -- Make sure that the parent page exists
                # --  and create if it doesn't
                # -----------------------------------------
                if not self.find_page_id(parent_page):
                    self.sync_page(parent_page, None, SECTION_PAGE_CONTENT)
                for path in page.url.rsplit("/", 2)[0].split("/"):
                    logger.debug(f"path is {path}")
                    parent_id = self.find_page_id(parent_page)
                    if path:
                        if page_name:
                            page_name = page_name + " " + path
                        else:
                            page_name = path
                        logger.info(f"will create a page {page_name} under the {parent_page}")
                        self.sync_page(page_name, parent_id, SECTION_PAGE_CONTENT)
                        self.pages.append(page_name)
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
                self.sync_page(confluence_page_name, parent_id, new_markdown)
                self.pages.append(confluence_page_name)
                if not page.url and self.config["set_homepage"]:
                    self.set_homepage(confluence_page_name)

                if attachments:
                    logger.debug(f"uploading attachments to the {page.title} page")
                for attachment in attachments:
                    logger.debug(f"trying to upload {attachment} to {confluence_page_name}")
                    if self.enabled:
                        try: 
                            self.sync_attachments(confluence_page_name, attachment)
                        except Exception as Argument:
                            logger.warning(Argument)
            except Exception as exp:
                logger.error(exp)
            return markdown

    def on_post_build(self, config):
        if self.enabled:
            #pages_upstream = [p['title'] for p in self.confluence.get_all_pages_from_space(self.config["space"], start=0, limit=99999, status=None, expand=None, content_type='page')]
            pages_upstream = [p['title'] for p in self.confluence.get_all_pages_by_label(PAGE_LABEL, start=0, limit=9999999)]
            for page in pages_upstream:
                if page not in self.pages:
                    logger.info(f"the page {page} is presented in confluence but is removed from mkdocs")
                    if self.config["cleanup"]:
                        self.confluence.remove_page(self.find_page_id(page))

    def on_page_content(self, html, page, config, files):
        return html

    def __get_page_url(self, section):
        return re.search("url='(.*)'\\)", section).group(1)[:-1] + ".md"

    def __get_page_name(self, section):
        return os.path.basename(re.search("url='(.*)'\\)", section).group(1)[:-1])

    def __get_section_name(self, section):
        return os.path.basename(re.search("url='(.*)'\\/", section).group(1)[:-1])

    def __get_section_title(self, section):
        try:
            r = re.search("Section\\(title='(.*)'\\)", section)
            return r.group(1)
        except AttributeError:
            name = self.__get_section_name(section)
            logger.warning(f"section '{name}' doesn't exist in the mkdocs.yml nav section!")
            return name

    def __get_page_title(self, section):
        try:
            r = re.search("\\s*Page\\(title='(.*)',", section)
            return r.group(1)
        except AttributeError:
            name = self.__get_page_url(section)
            logger.warning(f"page '{name}' doesn't exist in the mkdocs.yml nav section!")
            return name

    # Adapted from https://stackoverflow.com/a/3431838
    def get_file_sha1(self, file_path):
        hash_sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha1.update(chunk)
        return hash_sha1.hexdigest()

    def sync_attachments(self, page_name, filepath):
        logger.debug(f"adding an attachment: PAGE NAME: {page_name}, FILE: {filepath}")
        page_id = self.find_page_id(page_name)
        if page_id:
            file_hash = self.get_file_sha1(filepath)
            name = os.path.basename(filepath)
            self.confluence.attach_file(filepath, name=name, content_type=None, page_id=self.find_page_id(page_name), title=name, space=self.config["space"], comment=file_hash)
        else:
            logger.debug(f"page {page_name} doesn't exists")

    def find_page_id(self, page_name):
        logger.info(f"looking for a page id of the page: {page_name}")
        page_id = self.confluence.get_page_id(self.config["space"], page_name)
        if page_id is None:
            logger.info(f"page {page_name} can't be found")
        return page_id

    def sync_page(self, page_name, parent_page_id, page_content):
        logger.info(f"creating a new page: {page_name} under page with ID: {parent_page_id}")        
        if not self.dryrun:
            page_id = self.find_page_id(page_name)
            if not page_id:
                self.confluence.create_page(self.config["space"], page_name, page_content, parent_id=parent_page_id)
                self.confluence.set_page_label(self.find_page_id(page_name), PAGE_LABEL)
            else:
                result = self.confluence.update_page(page_id, page_name, page_content, parent_id=parent_page_id)
                self.confluence.set_page_label(page_id, PAGE_LABEL)

    def set_homepage(self, page_name):
        page_id = self.find_page_id(page_name)
        url = self.config["host_url"] + "/rest/api/space/" + self.config["space"]
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        # data = {"homepage": {"id": page_id}} 
        if not self.dryrun:
            try:
                r = self.session.get(url, headers=headers)
                r.raise_for_status()
                with nostdout():
                    response_json = r.json()
            except Exception as exp:
                logger.error(exp)
            response_json['homepage'] = { "id": page_id }
            try:
                r = self.session.put(url, json=response_json, headers=headers)
                r.raise_for_status()
            except Exception as exp:
                logger.error(exp)
            if r.status_code == 200:
                logger.info(f"a page with this id is now a homepage in the space: {page_id}")
            else:
                logger.error(f"can't set homepage to: {page_id}")
