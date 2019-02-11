from __future__ import absolute_import
from cbapi.errors import ApiError
from cbapi.models import NewBaseModel, CreatableModelMixin
import logging
from cbapi.psc.threathunter.query import Query, AsyncProcessQuery, TreeQuery, FeedQuery, ReportQuery
import validators

log = logging.getLogger(__name__)


class UnrefreshableModel(NewBaseModel):
    """Represents a model that can't be refreshed, i.e. for which ``reset()``
    is not a valid operation.
    """
    def refresh(self):
        raise ApiError("refresh() called on an unrefreshable model")


class Process(UnrefreshableModel):
    """Represents a process retrieved by one of the CbTH endpoints.
    """
    default_sort = 'last_update desc'
    primary_key = "process_guid"
    validation_url = "/pscr/query/v1/validate"

    @classmethod
    def _query_implementation(cls, cb):
        # This will emulate a synchronous process query, for now.
        return AsyncProcessQuery(cls, cb)

    def __init__(self, cb,  model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        super(Process, self).__init__(cb, model_unique_id=model_unique_id, initial_data=initial_data,
                                      force_init=force_init, full_doc=full_doc)

    def events(self, **kwargs):
        """Returns a query for events associated with this process's process GUID.

        :param kwargs: Arguments to filter the event query with.
        :return: Returns a Query object with the appropriate search parameters for events
        :rtype: :py:class:`cbapi.psc.threathunter.query.Query`

        Example::

        >>> [print(event) for event in process.events()]
        >>> [print(event) for event in process.events(event_type="modload")]
        """
        query = self._cb.select(Event).where(process_guid=self.process_guid)

        if kwargs:
            query = query.and_(**kwargs)

        return query

    def tree(self):
        """Returns a :py:class:`Tree` of children (and possibly siblings) associated with this process.

        :return: Returns a :py:class:`Tree` object
        :rtype: :py:class:`Tree`

        Example:

        >>> tree = process.tree()
        """
        data = self._cb.select(Tree).where(process_guid=self.process_guid).all()
        return Tree(self._cb, initial_data=data)

    @property
    def parents(self):
        """Returns a query for parent processes associated with this process.

        :return: Returns a Query object with the appropriate search parameters for parent processes, or None if the process has no recorded parent
        :rtype: :py:class:`cbapi.psc.threathunter.query.AsyncProcessQuery` or None
        """
        if "parent_guid" in self._info:
            return self._cb.select(Process).where(process_guid=self.parent_guid)
        else:
            return []

    @property
    def children(self):
        """Returns a list of child processes for this process.

        :return: Returns a list of process objects
        :rtype: list of :py:class:`Process`
        """
        return self.tree().children

    @property
    def siblings(self):
        # NOTE(ww): This shold be provided by the /tree endpoint eventually,
        # but currently isn't.
        raise ApiError("siblings() unimplemented")

    @property
    def process_md5(self):
        """Returns a string representation of the MD5 hash for this process.

        :return: A string representation of the process's MD5.
        :rtype: str
        """
        # NOTE: We have to check _info instead of poking the attribute directly
        # to avoid the missing attrbute login in NewBaseModel.
        if "process_hash" in self._info:
            return next((hsh for hsh in self.process_hash if len(hsh) == 32), None)
        else:
            return None

    @property
    def process_sha256(self):
        """Returns a string representation of the SHA256 hash for this process.

        :return: A string representation of the process's SHA256.
        :rtype: str
        """
        if "process_hash" in self._info:
            return next((hsh for hsh in self.process_hash if len(hsh) == 64), None)
        else:
            return None

    @property
    def process_pids(self):
        """Returns a list of PIDs associated with this process.

        :return: A list of PIDs
        :rtype: list of ints
        """
        # NOTE(ww): This exists because the API returns the list as "process_pid",
        # which is misleading. We just give a slightly clearer name.
        return self.process_pid

    def __repr__(self):
        return "<%s.%s: process id %s document id %s> @ %s" % (self.__class__.__module__, self.__class__.__name__,
                                                               self.process_guid, self.document_guid,
                                                               self._cb.session.server)


class Event(UnrefreshableModel):
    """Events can be queried for via ``CbThreatHunterAPI.select``
    or though an already selected process with ``Process.events()``.
    """
    urlobject = '/pscr/query/v1/events'
    validation_url = '/pscr/query/v1/events/validate'
    default_sort = 'last_update desc'
    primary_key = "process_guid"

    @classmethod
    def _query_implementation(cls, cb):
        return Query(cls, cb)

    def __init__(self, cb,  model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        super(Event, self).__init__(cb, model_unique_id=model_unique_id, initial_data=initial_data,
                                    force_init=force_init, full_doc=full_doc)


class Tree(UnrefreshableModel):
    """The preferred interface for interacting with Tree models
    is ``Process.tree()``.
    """
    urlobject = '/pscr/query/v2/tree'
    primary_key = 'process_guid'

    @classmethod
    def _query_implementation(cls, cb):
        return TreeQuery(cls, cb)

    def __init__(self, cb, model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        super(Tree, self).__init__(cb, model_unique_id=model_unique_id, initial_data=initial_data,
                                   force_init=force_init, full_doc=full_doc)

    @property
    def children(self):
        """Returns all of the children of the process that this tree is centered around.

        :return: A list of :py:class:`Process` instances
        :rtype: list of :py:class:`Process`
        """
        return [Process(self._cb, initial_data=child) for child in self.nodes["children"]]


class Feed(UnrefreshableModel, CreatableModelMixin):
    """Represents a ThreatHunter feed's metadata.
    """
    urlobject = "/threathunter/feedmgr/v1/feed"
    primary_key = "id"
    validation_map = {
        "name": {
            "func": lambda x: type(x) == str,
        },
        "owner": {
            "func": lambda x: type(x) == str,
        },
        "provider_url": {
            "func": validators.url,
        },
        "summary": {
            "func": lambda x: type(x) == str,
        },
        "category": {
            "func": lambda x: type(x) == str,
        },
        "access": {
            "func": lambda x: type(x) == str and x in ["public", "private"],
        },
        "id": {
            "required": False,
            "func": lambda x: type(x) == str,
        }
    }

    @classmethod
    def _query_implementation(cls, cb):
        return FeedQuery(cls, cb)

    def __init__(self, cb, model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        item = {}
        reports = []

        if initial_data:
            # NOTE(ww): Some endpoints give us the full Feed, others give us just the FeedInfo.
            if "feedinfo" in initial_data:
                item = initial_data["feedinfo"]
                reports = initial_data.get("reports", [])
            else:
                item = initial_data
        elif model_unique_id:
            # TODO(ww): It's probably bad practice to make a request here.
            # Maybe abstract this into a separate method?
            resp = cb.get_object("/threathunter/feedmgr/v1/feed/{}".format(model_unique_id))
            item = resp.get("feedinfo", {})
            reports = resp.get("reports", [])

        super(Feed, self).__init__(cb, model_unique_id=item.get("id", None), initial_data=item,
                                   force_init=force_init, full_doc=full_doc)

        self._reports = [Report(cb, initial_data=report) for report in reports]

    def _create(self):
        self._validate()

        body = {
            'feedinfo': self._info,
            'reports': [report._info for report in self._reports],
        }

        new_info = self._cb.post_object("/threathunter/feedmgr/v1/feed", body).json()
        self._info.update(new_info)
        return self

    def _validate(self):
        for key, value in self._info.items():
            if key not in self.validation_map:
                raise ApiError("unexpected field: {}".format(key))

        for key, validation in self.validation_map.items():
            if key not in self._info and validation.get("required", True):
                raise ApiError("required field missing: {}".format(key))
            if key in self._info and not validation["func"](self._info[key]):
                raise ApiError("invalid field: {}".format(key))

        for report in self._reports:
            report._validate()

        # TODO(ww): Any other field-specific validation required?

    def delete(self):
        if not self.id:
            raise ApiError("missing feed ID")

        self._cb.delete_object("/threathunter/feedmgr/v1/feed/{}".format(self.id))

    def update(self, **kwargs):
        if not self.id:
            raise ApiError("missing feed ID")

        for key, value in kwargs.items():
            if key not in self._info:
                raise ApiError("can't update nonexistent field {}".format(key))

        new_info = self._cb.put_object("/threathunter/feedmgr/v1/feed/{}/feedinfo".format(self.id), kwargs).json()
        self._info.update(new_info)
        return self

    def reports(self):
        # TODO(ww): Short circuit on self._reports?
        return self._cb.select(Report).where(feed_id=self.id)

    def replace(self, append=False):
        pass


class Report(UnrefreshableModel, CreatableModelMixin):
    """Represents reports retrieved from a ThreatHunter feed.
    """
    urlobject = "/threathunter/feedmgr/v1/feed/{}/report"
    primary_key = "id"
    # TODO(ww): docs say that id is required, but that doesn't make sense in the context
    # of report creation.
    validation_map = {
        "id": {
            "required": False,
            "func": lambda x: type(x) == str,
        },
        "timestamp": {
            "func": lambda x: type(x) == int,
        },
        "title": {
            "func": lambda x: type(x) == str,
        },
        "description": {
            "func": lambda x: type(x) == str,
        },
        "severity": {
            "func": lambda x: type(x) == int,
        },
        "link": {
            "required": False,
            "func": validators.url,
        },
        "tags": {
            "required": False,
            "func": lambda xs: type(xs) == list and all(type(x) == str for x in xs),
        },
        "iocs": {
            "required": False,
            "func": lambda xs: type(xs) == list and all(isinstance(x, IOC) for x in xs),
        },
        "iocs_v2": {
            "required": False,
            "func": lambda xs: type(xs) == list and all(isinstance(x, IOC_v2) for x in xs),
        },
        "visibility": {
            "required": False,
            "func": lambda x: type(x) == str and x in ["public", "private"],
        },
    }

    @classmethod
    def _query_implementation(cls, cb):
        return ReportQuery(cls, cb)

    def __init__(self, cb, model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        super(Report, self).__init__(cb, model_unique_id=initial_data["id"], initial_data=initial_data,
                                     force_init=force_init, full_doc=full_doc)

        self._iocs = self.iocs
        self._iocs_v2 = self._iocs_v2

    def _validate(self):
        for key, value in self._info.items():
            if key not in self.validation_map:
                raise ApiError("unexpected field: {}".format(key))

        for key, validation in self.validation_map.items():
            if key not in self._info and validation.get("required", True):
                raise ApiError("required field missing: {}".format(key))
            if key in self._info and not validation["func"](self._info[key]):
                raise ApiError("invalid field: {}".format(key))

    def delete(self):
        if not self.id:
            raise ApiError("missing Report ID")

        # TODO(ww): Problem: Report deletion requires the feed ID.
        # self._cb.delete_object("/threathunter/feedmgr/v1/feed/")

    def iocs(self):
        pass


class Watchlist(UnrefreshableModel):
    pass


class IOC(UnrefreshableModel):
    def __init__(self, cb, model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        if not initial_data:
            raise ApiError("IOC can only be initialized from initial_data")

        super(Report, self).__init__(cb, model_unique_id=model_unique_id, initial_data=initial_data,
                                     force_init=force_init, full_doc=full_doc)

    def _validate(self):
        pass
    pass


class IOC_v2(UnrefreshableModel):
    primary_key = "id"

    def __init__(self, cb, model_unique_id=None, initial_data=None, force_init=False, full_doc=True):
        if not initial_data:
            raise ApiError("IOC can only be initialized from initial_data")

        super(Report, self).__init__(cb, model_unique_id=initial_data["id"], initial_data=initial_data,
                                     force_init=force_init, full_doc=full_doc)

    def _validate(self):
        pass
    pass
