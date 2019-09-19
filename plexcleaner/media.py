import string
import os
import hashlib
import json

from pyjarowinkler import distance
import unidecode

from plexcleaner import LOG

__author__ = 'Jean-Bernard Ratte - jean.bernard.ratte@unary.ca'


class Library(object):
    _B_TO_GB = 9.3132257461547852e-10

    def __init__(self, db, config={}):
        self.library = []
        self.library_paths = []
        self.effective_size = 0
        self.has_missing_file = False

        for row in db.get_rows():
            LOG.debug(u'=== Library class; db row: {0}'.format(row))
            movie = Movie(*row, config=config)
            self._update_library(movie)

        LOG.info("There are {0} different media source".format(
            len(self.library_paths)))
        LOG.info("Library size is {0:0.3f} gigabyte".format(
            self.effective_size * self._B_TO_GB))

    def _update_library(self, movie):
        original_movie_file = _str_to_unicode(movie.original_file)
        if int(movie.count) > 1:
            LOG.warning(
                u"Movie {0} has duplicate file. Will not process.".format(
                    original_movie_file))
            return False

        self.library.append(movie)

        if movie.library_path not in self.library_paths:
            self.library_paths.append(movie.library_path)

        if movie.exist and movie.matched:  # Movie might be in the database but it might be absent in the filesystem
            self.effective_size += movie.size

        if not movie.exist:
            self.has_missing_file = True
            LOG.warning(u"The file {0} is missing from the library".format(
                original_movie_file))

    def __iter__(self):
        for m in self.library:
            yield m

    def __len__(self):
        return len(self.library)


def _str_to_unicode(s):
    try:
        return unicode(s, 'UTF-8')
    except TypeError:  # s is already unicode
        return s


class NullConfig():
    remove_from_path = None
    append_to_path = None


class Movie(object):
    """ Describe movie file as it can be found in the Plex Database
    """
    _metadata_path = u'Library/Application Support/Plex Media Server/Metadata/Movies'
    _jacket_path = u"{0}/{1}.bundle/Contents/_stored/{2}"

    def __init__(self,
                 mid,
                 title,
                 original_file,
                 year,
                 size,
                 fps,
                 guid,
                 count,
                 jacket,
                 library_path,
                 studio=None,
                 tags_star=None,
                 config=NullConfig):
        self.mid = mid
        self.original_file = _str_to_unicode(original_file)

        if config.remove_from_path:
            remove_from_path = r'{0}/'.format(config.remove_from_path)
            self.original_file = _str_to_unicode(
                self.original_file.replace(remove_from_path, ''))

        if config.append_to_path:
            self.original_file = u'{0}{1}'.format(config.append_to_path,
                                                  self.original_file)

        self.filepath = _str_to_unicode(os.path.dirname(self.original_file))
        self.basename = _str_to_unicode(os.path.basename(self.original_file))
        self.filename, self.file_ext = [
            _str_to_unicode(s) for s in os.path.splitext(self.basename)
        ]

        self.title = _str_to_unicode(title)
        self.correct_title = self._clean_filename()

        try:
            self.title_distance = distance.get_jaro_distance(
                self.title, self.correct_title)
        except distance.JaroDistanceException:
            self.title_distance = 0

        if year:
            self.year = _str_to_unicode(year)
        else:
            self.year = None

        self.size = size
        self.fps = fps
        self.exist = os.path.exists(self.original_file)
        self.matched = not guid.startswith('local://')
        self.count = count

        self.library_path = _str_to_unicode(library_path)

        if self.matched:
            h = hashlib.sha1(guid).hexdigest()
            self.relative_jacket_path = _str_to_unicode(
                os.path.join(self._jacket_path.format(h[0], h[1:],
                                                      jacket[11:])))
            self.studio = _str_to_unicode(studio)
            # LOG.debug(u'=== Media class; self.studio: {0}'.format(self.studio))

            if tags_star:
                # LOG.debug(u'=== Media class; tags_star: {0}'.format(tags_star))
                self.actors = [
                    _str_to_unicode(actor) for actor in tags_star.split("|")
                ]
            else:
                self.actors = []

    def _clean_filename(self, replacements=None):
        if not replacements:
            replacements = [('&', 'and')]

        cleaned = self.title
        for r in replacements:
            cleaned = cleaned.replace(*r)

        # return ''.join(char for char in cleaned if char in "-_.()' {0}{1}".format(string.ascii_letters, string.digits))
        # LOG.debug(u'=== Media class; _clean_filename: {0}'.format(cleaned))
        return cleaned

    def get_correct_directory(self):
        directory = u"{0} ({1})".format(self.correct_title, self.year)
        if self.studio:
            directory = u"{0} - {1}".format(self.studio, directory)

        # LOG.debug(
        #     u'=== Media class; get_correct_directory: {0}'.format(directory))
        return directory

    def get_correct_filename(self):
        filename = u""

        if self.studio:
            filename = self.studio

        if self.year:
            if filename:
                filename = u"{0} - {1}".format(filename, self.year)

            else:
                filename = self.year

        if self.actors:
            actors_string = _str_to_unicode(self.actors.join(" - "))

            if filename:
                filename = u"{0} - {1}".format(filename, actors_string)
            else:
                filename = actors_string

        if filename:
            filename = u"{0} - {1}".format(filename, self.correct_title)
        else:
            filename = self.correct_title

        filename = u"{0}{1}".format(filename, self.file_ext)
        # LOG.debug(
        #     u'=== Media class; get_correct_filename: {0}'.format(filename))
        return filename

    def get_correct_path(self):
        if self.get_correct_directory() == os.path.basename(self.filepath):
            return self.get_correct_filename()

        return _str_to_unicode(
            os.path.join(self.get_correct_directory(),
                         self.get_correct_filename()))

    def get_correct_absolute_file(self, override=None):
        if override:
            return _str_to_unicode(
                os.path.join(override, self.get_correct_path()))

        return _str_to_unicode(
            os.path.join(self.filepath, self.get_correct_path()))

    def get_correct_absolute_path(self, override=None):
        directory = u"{0} ({1})".format(self.correct_title, self.year)
        if override:
            return _str_to_unicode(os.path.join(override, directory))

        if directory == os.path.basename(self.filepath):
            return self.filepath

        return _str_to_unicode(os.path.join(self.filepath, directory))

    def get_metadata_jacket(self, metadata_home='/var/lib/plexmediaserver'):
        if not self.matched:
            return None

        return _str_to_unicode(
            os.path.join(metadata_home, self._metadata_path,
                         self.relative_jacket_path))

    def need_update(self, override=None):
        return not self.get_correct_absolute_file(
            override=override) == self.original_file

    def __str__(self):
        serialized = dict()
        attributes = [a for a in dir(self) if not a.startswith('_')]

        for attribute in attributes:
            if callable(self.__getattribute__(attribute)):
                serialized.update({
                    attribute.replace('get_', ''):
                    getattr(self, attribute)()
                })

            else:
                serialized.update(
                    {attribute: self.__getattribute__(attribute)})

        return json.dumps(serialized)
