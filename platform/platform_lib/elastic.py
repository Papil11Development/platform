from typing import Optional
from urllib.parse import urlparse
from elasticsearch_dsl import Date, Document, InnerDoc, Text, Long, connections, Search, Index, Boolean, A, Q
from django.conf import settings


if settings.ENABLE_ELK:
    connections.create_connection(headers=settings.ELASTIC_HEADERS_EXT, host=settings.ELASTIC_HOST_EXT,
                                  port=settings.ELASTIC_PORT_EXT,
                                  use_ssl=False)


class TimeRange(InnerDoc):
    time_start = Date()
    time_end = Date()


class RoiField(InnerDoc):
    id = Text()
    title = Text()
    time_start = Date()
    time_end = Date()


class ActionsField(InnerDoc):
    kind = Text()
    direction = Text()


class Activity(Document):
    id = Text()
    time_start = Date()
    time_end = Date()
    person_id = Text()
    creation_date = Date()
    age = Long()
    gender = Text()
    angry = TimeRange()
    surprised = TimeRange()
    neutral = TimeRange()
    happy = TimeRange()
    is_staff = Boolean()
    location_id = Text()
    location_title = Text()
    roi = RoiField()
    first_visit = Boolean()
    watcher = TimeRange()
    medias = Text()
    actions = ActionsField()

    @staticmethod
    def get_elastic_activities(index: str, person_id: Optional[str] = None) -> set:
        try:
            if person_id is None:
                search = Search(index=index).query(Q(
                    'bool', must_not=[Q('exists', field='person_id.keyword')]
                ))
            else:
                search = Search(index=index).query('match', person_id__keyword=person_id)
            aggregation = A('terms', field='id.keyword', size=settings.ELASTIC_UNLOCK_RESPONSE_SIZE)
            search.aggs.metric('activity_id', aggregation)
            response = search.execute().to_dict()
            set_kibana_activity = set()
            for activity in response.get('aggregations').get('activity_id').get('buckets'):
                set_kibana_activity.add(activity.get('key'))
            return set_kibana_activity
        except Exception as ex:
            print('Exception in get_elastic_activities:', ex)
            return set()

    @staticmethod
    def get_last_elastic_activity(index, person_id=None):
        try:
            search = Search(index=index)
            if person_id:
                search = search.query('match', person_id__keyword=str(person_id))
            return search.sort('-creation_date').extra(size=1).execute()[0].creation_date
        except IndexError:
            return None

    @staticmethod
    def is_index_exist(index):
        try:
            return Index(index).exists()
        except Exception as ex:
            print('Exception in is_index_exist:', ex)

    @staticmethod
    def request_delete(index, person_ids):
        for person in person_ids:
            search_delete = Search(index=index).query('match', person_id__keyword=person)
            response = search_delete.delete()
            check = response.to_dict()
            if check.get('error'):
                raise Exception(check['error'])

    @staticmethod
    def synchronize_data(index, persons_na):

        set_persons = set([str(elem) for elem in map(str, list(persons_na.values_list('id', flat=True)))])
        search_persons = Search(index=index)

        aggregation = A('terms', field='person_id.keyword', size=settings.ELASTIC_UNLOCK_RESPONSE_SIZE)
        search_persons.aggs.metric('list_persons', aggregation)
        response = search_persons.execute().to_dict()
        persons_kibana = response.get('aggregations').get('list_persons').get('buckets')
        deleted_persons = 0

        if len(persons_kibana) > len(set_persons):

            set_kibana_persons = set()

            for person in persons_kibana:
                set_kibana_persons.add(person.get('key'))

            diff = set_kibana_persons - set_persons
            for record in diff:
                try:
                    search_delete = Search(index=index).query('match', person_id__keyword=record)
                    search_delete.delete()
                    deleted_persons += 1
                except Exception as ex:
                    print(f'Message: {ex}')
        return deleted_persons
