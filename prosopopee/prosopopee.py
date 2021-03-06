#!/usr/bin/env python

import os
import yaml
import shutil

from path import Path

from jinja2 import Environment, FileSystemLoader

from .cache import CACHE
from .utils import error, warning, okgreen


DEFAULTS = {
    "rss": True,
    "share": False,
    "settings": {},
    "show_date": True,
}

SETTINGS = {
    "gm": {
        "quality": 75,
        "auto-orient": True,
        "strip": True,
        "resize": None,
        "progressive": True
    },
    "ffmpeg": {
        "binary": "ffmpeg",
        "loglevel": "error",
        "format": "webm",
        "resolution": "1280x720",
        "vbitrate": "3900k",
        "abitrate": "100k",
        "audio": "libvorbis",
        "video": "libvpx",
        "other": "-qmin 10 -qmax 42 -maxrate 500k -bufsize 1500k"
    }
}


class Video(object):
    base_dir = Path()
    target_dir = Path()

    def __init__(self, options):
        error(SETTINGS["ffmpeg"] is not False, "I couldn't find a binary to convert video and I ask to do so, abort")

        # assuming string
        if not isinstance(options, dict):
            options = {"name": options}
        # used for caching, if it's modified -> regenerate
        self.options = SETTINGS["ffmpeg"].copy()
        self.options.update(options)

    @property
    def name(self):
        return self.options["name"]

    def ffmpeg(self, source, target, options):
        if not CACHE.needs_to_be_generated(source, target, options):
            okgreen("Skipped", source + " is already generated")
            return

        ffmpeg_switches = {
           "source": source,
           "target": target,
           "loglevel": "-loglevel %s" % options["loglevel"],
           "resolution": "-s %s" % options["resolution"],
           "resize": "-vf scale=-1:%s" % options.get("resize"),
           "vbitrate": "-b:v %s" % options["vbitrate"],
           "abitrate": "-b:v %s" % options["abitrate"],
           "format": "-f %s" % options["format"],
           "binary": "%s" % options["binary"],
           "video": "-c:v %s" % options["video"],
           "audio": "-c:a %s" % options["audio"],
           "other": "%s" % options["other"]
        }

        warning("Generation", source)

        if options.get("resize"):
            command = "{binary} {loglevel} -i {source} {resize} -vframes 1 -y {target}".format(**ffmpeg_switches)
            print(command)
            error(os.system(command) == 0, "%s command failed" % ffmpeg_switches["binary"])
        else:
            command = "{binary} {loglevel} -i {source} {video} {vbitrate} {other} {audio} {abitrate} {resolution} {format} -y {target}".format(**ffmpeg_switches)
            print(command)
            error(os.system(command) == 0, "%s command failed" % ffmpeg_switches["binary"])

        CACHE.cache_picture(source, target, options)

    def copy(self):
        source, target = self.base_dir.joinpath(self.name), self.target_dir.joinpath(self.name)
        options = self.options.copy()
        self.ffmpeg(source, target, options)
        return ""

    def generate_thumbnail(self, gm_geometry):
        thumbnail_name = ".".join(self.name.split(".")[:-1]) + "-%s.jpg" % gm_geometry

        source, target = self.base_dir.joinpath(self.name), self.target_dir.joinpath(thumbnail_name)

        options = self.options.copy()
        options.update({"resize": gm_geometry})

        self.ffmpeg(source, target, options)

        return thumbnail_name

    def __repr__(self):
        return self.name


class Image(object):
    base_dir = ""
    target_dir = ""

    def __init__(self, options):
        # assuming string
        if not isinstance(options, dict):
            options = {"name": options}

        self.options = SETTINGS["gm"].copy()  # used for caching, if it's modified -> regenerate
        self.options.update(options)

    @property
    def name(self):
        return self.options["name"]

    def gm(self, source, target, options):
        if not CACHE.needs_to_be_generated(source, target, options):
            okgreen("Skipped", source + " is already generated")
            return

        gm_switches = {
           "source": source,
           "target": target,
           "auto-orient": "-auto-orient" if options["auto-orient"] else "",
           "strip": "-strip" if options["strip"] else "",
           "quality": "-quality %s" % options["quality"] if "quality" in options else "-define jpeg:preserve-settings",
           "resize": "-resize %s" % options["resize"] if options.get("resize", None) is not None else "",
           "progressive": "-interlace Line" if options.get("progressive", None) is True else ""
        }

        command = "gm convert '{source}' {auto-orient} {strip} {progressive} {quality} {resize} '{target}'".format(**gm_switches)
        warning("Generation", source)

        print(command)
        error(os.system(command) == 0, "gm command failed")

        CACHE.cache_picture(source, target, options)

    def copy(self):
        source, target = self.base_dir.joinpath(self.name), self.target_dir.joinpath(self.name)

        # XXX doing this DOESN'T improve perf at all (or something like 0.1%)
        # if os.path.exists(target) and os.path.getsize(source) == os.path.getsize(target):
        # print "Skipped %s since the file hasn't been modified based on file size" % source
        # return ""

        options = self.options.copy()

        if not options["auto-orient"] and not options["strip"]:
            shutil.copyfile(source, target)
            print("%s%s%s" % (source, "->", target))
        else:
            # Do not consider quality settings here, since we aim to copy the input image
            # better to preserve input encoding setting
            del options["quality"]
            self.gm(source, target, options)

        return ""

    def generate_thumbnail(self, gm_geometry):
        thumbnail_name = ".".join(self.name.split(".")[:-1]) + "-" + gm_geometry + "." + self.name.split(".")[-1]

        source, target = self.base_dir.joinpath(self.name), self.target_dir.joinpath(thumbnail_name)

        options = self.options.copy()
        options.update({"resize": gm_geometry})

        self.gm(source, target, options)

        return thumbnail_name

    def __repr__(self):
        return self.name


def get_settings():
    error(Path("settings.yaml").exists(), "I can't find a "
          "settings.yaml in the current working directory")

    settings = yaml.safe_load(open("settings.yaml", "r"))

    error(isinstance(settings, dict), "Your settings.yaml should be a dict")

    for key, value in DEFAULTS.items():
        if key not in settings:
            settings[key] = value

    if settings["settings"].get("ffmpeg"):
        SETTINGS["ffmpeg"].update(settings["settings"]["ffmpeg"])

        conv_video = settings["settings"]["ffmpeg"]["binary"]
    else:
        conv_video = "ffmpeg"

    error(os.system("which gm > /dev/null") == 0, "I can't locate the gm binary, "
          "please install the 'graphicsmagick' package.\n")

    if os.system("which " + conv_video + " > /dev/null") != 0:
        if conv_video == "ffmpeg" and os.system("which avconv > /dev/null") == 0:
            SETTINGS["ffmpeg"]["binary"] = "avconv"
            warning("Video", "I couldn't locate ffmpeg but I could find avconv, "
                             "switching to avconv for video conversion")
        else:
            warning("Video", "I can't locate the " + conv_video + " binary, "
                    "please install the '" + conv_video + "' package.\n")
            warning("Video", "I won't be able to encode video and I will stop if I encounter a video to convert")
            SETTINGS["ffmpeg"] = False

    error(settings.get("title"), "You need to specify a title in your main settings.yaml")

    if (settings["rss"] or settings["share"]) and not settings.get("url"):
        warning("warning", "If you want the rss and/or the social network share to work, "
                "you need to specify the website url in root settings")
        settings["rss"] = False
        settings["share"] = False

    if settings["settings"].get("gm"):
        SETTINGS["gm"].update(settings["settings"]["gm"])

    return settings


def get_gallery_templates(theme, gallery_path="", parent_templates=None):
    theme_path = Path(__file__).parent.joinpath("themes", theme).exists()

    available_themes = theme, "', '".join(Path(__file__).parent.joinpath("themes").listdir())

    error(theme_path, "'%s' is not an existing theme, available themes are '%s'" % available_themes)

    templates_dir = [
        Path(".").joinpath("templates").realpath(),
        Path(__file__).parent.joinpath("themes", theme, "templates")
    ]

    if theme != "exposure":
        templates_dir.append(Path(__file__).parent.joinpath("themes", "exposure", "templates"))

    subgallery_templates = Environment(loader=FileSystemLoader(templates_dir), trim_blocks=True)

    Path(".").joinpath("build", gallery_path, "static").rmtree_p()

    if Path(".").joinpath("static").exists():
        shutil.copytree(Path(".").joinpath("static"), Path(".").joinpath("build", gallery_path, "static"))

    else:
        shutil.copytree(
            Path(__file__).parent.joinpath("themes", theme, "static"),
            Path(".").joinpath("build", gallery_path, "static")
        )

    return subgallery_templates


def process_directory(gallery_name, settings, parent_templates, parent_gallery_path=False):
    if parent_gallery_path:
        gallery_path = parent_gallery_path.joinpath(gallery_name)
    else:
        gallery_path = gallery_name

    gallery_settings = yaml.safe_load(open(Path(".").joinpath(gallery_path, "settings.yaml").abspath(), "r"))

    error(isinstance(gallery_settings, dict), "Your %s should be a dict" % gallery_name.joinpath("settings.yaml"))
    error(gallery_settings.get("title"), "You should specify a title in %s" % gallery_name.joinpath("settings.yaml"))

    gallery_cover = {}

    sub_galleries = [x for x in Path(".").joinpath(gallery_path).listdir() if x.joinpath("settings.yaml").exists()]

    Path("build").joinpath(gallery_path).makedirs_p()

    if not gallery_settings.get("public", True):
        build_gallery(settings, gallery_settings, gallery_path, parent_templates)
    else:
        gallery_cover = create_cover(gallery_name, gallery_settings, gallery_path)

        if not sub_galleries:
            build_gallery(settings, gallery_settings, gallery_path, parent_templates)

        else:
            error(gallery_settings.get("sections") is not False,
                  "The gallery in %s can't have both sections and subgalleries" % gallery_name.joinpath("settings.yaml"))

            # Sub galleries found, create index with them instead of a gallery
            theme = gallery_settings.get("theme", settings.get("theme", "exposure"))

            subgallery_templates = get_gallery_templates(theme, gallery_path, parent_templates)
            sub_page_galleries_cover = []

            for subgallery in sub_galleries:
                sub_page_galleries_cover.append(
                    process_directory(subgallery.name, settings, subgallery_templates, gallery_path)
                )

            build_index(settings, sub_page_galleries_cover, subgallery_templates, gallery_path, sub_index=True)
            gallery_cover['sub_gallery'] = sub_page_galleries_cover

    return gallery_cover


def create_cover(gallery_name, gallery_settings, gallery_path):
    error(gallery_settings.get("title"), "Your gallery describe in %s need to have a "
                                         "title" % gallery_name.joinpath("settings.yaml"))

    error(gallery_settings.get("cover"), "You should specify a path to a cover picture "
                                         "in %s" % gallery_name.joinpath("settings.yaml"))

    if isinstance(gallery_settings["cover"], dict):
        cover_image_path = gallery_path.joinpath(gallery_settings["cover"]["name"])
        cover_image_url = gallery_name.joinpath(gallery_settings["cover"]["name"])
        cover_image_type = gallery_settings["cover"]["type"]
    else:
        cover_image_path = gallery_path.joinpath(gallery_settings["cover"])
        cover_image_url = gallery_name.joinpath(gallery_settings["cover"])
        cover_image_type = "image"

    error(cover_image_path.exists(), "File for %s cover image doesn't exist at "
                                            "%s" % (gallery_name, cover_image_path))

    gallery_cover = {
        "title": gallery_settings["title"],
        "link": gallery_name,
        "sub_title": gallery_settings.get("sub_title", ""),
        "date": gallery_settings.get("date", ""),
        "tags": gallery_settings.get("tags", ""),
        "cover_type": cover_image_type,
        "cover": cover_image_url,
    }
    return gallery_cover


def build_gallery(settings, gallery_settings, gallery_path, template):
    gallery_index_template = template.get_template("gallery-index.html")
    page_template = template.get_template("page.html")

    # this should probably be a factory
    Image.base_dir = Path(".").joinpath(gallery_path)
    Image.target_dir = Path(".").joinpath("build", gallery_path)

    Video.base_dir = Path(".").joinpath(gallery_path)
    Video.target_dir = Path(".").joinpath("build", gallery_path)

    template_to_render = page_template if gallery_settings.get("static") else gallery_index_template

    html = template_to_render.render(
        settings=settings,
        gallery=gallery_settings,
        Image=Image,
        Video=Video,
        link=gallery_path,
        name=gallery_path.split('/', 1)[-1]
    ).encode("Utf-8")

    open(Path("build").joinpath(gallery_path, "index.html"), "w").write(html)

    # XXX shouldn't this be a call to build_gallery?
    # Build light mode gallery
    if gallery_settings.get("light_mode", False) or (
                settings["settings"].get("light_mode", False) and\
                gallery_settings.get("light_mode") is None
            ):

        # Prepare light mode
        Path("build").joinpath(gallery_path, "light").makedirs_p()
        gallery_light_path = Path(gallery_path).joinpath("light")
        light_templates = get_gallery_templates("light", gallery_light_path)

        Image.base_dir = Path(".").joinpath(gallery_path)
        Image.target_dir = Path(".").joinpath("build", gallery_path)

        Video.base_dir = Path(".").joinpath(gallery_path)
        Video.target_dir = Path(".").joinpath("build", gallery_path)

        light_template_to_render = light_templates.get_template("gallery-index.html")

        html = light_template_to_render.render(
            settings=settings,
            gallery=gallery_settings,
            Image=Image,
            Video=Video,
            link=gallery_light_path,
            name=gallery_path.split('/', 1)[-1]
        ).encode("Utf-8")

        open(Path("build").joinpath(gallery_light_path, "index.html"), "w").write(html)

def build_index(settings, galleries_cover, templates, gallery_path='', sub_index=False):
    index_template = templates.get_template("index.html")

    galleries_cover = reversed(sorted(filter(lambda x: x != {}, galleries_cover), key=lambda x: x["date"]))

    # this should probably be a factory
    Image.base_dir = Path(".").joinpath(gallery_path)
    Image.target_dir = Path(".").joinpath("build", gallery_path)

    Video.base_dir = Path(".").joinpath(gallery_path)
    Video.target_dir = Path(".").joinpath("build", gallery_path)

    html = index_template.render(
        settings=settings,
        galleries=galleries_cover,
        sub_index=sub_index,
        Image=Image,
        Video=Video
    ).encode("Utf-8")

    open(Path("build").joinpath(gallery_path, "index.html"), "w").write(html)


def main():
    settings = get_settings()

    front_page_galleries_cover = []

    galleries_dirs = [x for x in Path(".").listdir() if x.joinpath("settings.yaml").exists()]

    error(galleries_dirs, "I can't find at least one directory with a settings.yaml in the current working "
          "directory (NOT the settings.yaml in your current directory, but one INSIDE A "
          "DIRECTORY in your current working directory), you don't have any gallery?")

    Path("build").makedirs_p()

    theme = settings["settings"].get("theme", "exposure")
    templates = get_gallery_templates(theme)
    templates.add_extension('jinja2.ext.with_')

    for gallery in galleries_dirs:
        front_page_galleries_cover.append(process_directory(gallery, settings, templates))

    if settings["rss"]:
        feed_template = templates.get_template("feed.xml")

        xml = feed_template.render(
            settings=settings,
            galleries=reversed(sorted(filter(lambda x: x != {}, front_page_galleries_cover), key=lambda x: x["date"]))
        ).encode("Utf-8")

        open(Path("build").joinpath("feed.xml"), "w").write(xml)

    build_index(settings, front_page_galleries_cover, templates)


if __name__ == '__main__':
    main()
