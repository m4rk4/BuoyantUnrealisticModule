import json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import drupal, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    return drupal.get_content(url, args, save_debug)


def get_item(news_json, args, save_debug):
    item = {}
    source_item = {}
    item['id'] = news_json['id']
    if news_json['attributes'].get('source_url'):
        item['url'] = news_json['attributes']['source_url']
        item['author'] = {"name": news_json['attributes']['source']}
        source_item = utils.get_content(item['url'], {}, False)
    item['title'] = news_json['attributes']['headline']

    dt = datetime.fromisoformat(news_json['attributes']['created'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(news_json['attributes']['changed'])
    item['date_modified'] = dt.isoformat()

    if news_json['relationships'].get('player') and news_json['relationships']['player'].get('data'):
        api_json = drupal.get_api_json('https://www.nbcsportsedge.com/api/', news_json['relationships']['player']['data']['type'], news_json['relationships']['player']['data']['id'])
        if api_json:
            if api_json['data']['relationships'].get('image') and api_json['data']['relationships']['image'].get('data'):
                item['_image'] = drupal.get_field_data(api_json['data']['relationships']['image']['data'], 'https://www.nbcsportsedge.com/api/', 'www.nbcsportsedge.com', None, None)

    if news_json['attributes'].get('analysis'):
        item['content_html'] = '<strong>{}</strong>'.format(news_json['attributes']['news']['processed'])
        item['content_html'] += news_json['attributes']['analysis']['processed']
    else:
        item['content_html'] = news_json['attributes']['news']['processed']
    if source_item:
        item['content_html'] += '<hr/>' + source_item['content_html']
        if not item.get('_image') and source_item.get('_image'):
            item['_image'] = source_item['_image']
    return item

def get_feed(args, save_debug=False):
    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', attrs={"data-drupal-selector": "drupal-settings-json"})
    if not el:
        logger.warning('unable to find drupal-settings-json')
        return None

    drupal_settings_json = json.loads(el.string)

    if '/player/' in args['url']:
        entity = next((it for it in drupal_settings_json['rwEntity'] if it['type'] == 'player'), None)
        api_url = 'https://www.nbcsportsedge.com/api/player_news?sort=-initial_published_date&page%5Blimit%5D=10&page%5Boffset%5D=0&filter%5Bplayer-group%5D%5Bgroup%5D%5Bconjunction%5D=OR&filter%5Bprimary-player-filter%5D%5Bcondition%5D%5Bpath%5D=player.meta.drupal_internal__id&filter%5Bprimary-player-filter%5D%5Bcondition%5D%5Bvalue%5D={0}&filter%5Bprimary-player-filter%5D%5Bcondition%5D%5Boperator%5D==&filter%5Bprimary-player-filter%5D%5Bcondition%5D%5BmemberOf%5D=player-group&filter%5Brelated-player-filter%5D%5Bcondition%5D%5Bpath%5D=related_players.meta.drupal_internal__id&filter%5Brelated-player-filter%5D%5Bcondition%5D%5Bvalue%5D={0}&filter%5Brelated-player-filter%5D%5Bcondition%5D%5Boperator%5D=IN&filter%5Brelated-player-filter%5D%5Bcondition%5D%5BmemberOf%5D=player-group&include=player,position,positions,team,team.secondary_logo,player.image,related_players,related_teams'.format(entity['id'])
    elif '/teams/' in args['url']:
        entity = next((it for it in drupal_settings_json['rwEntity'] if it['type'] == 'team'), None)
        api_url = 'https://www.nbcsportsedge.com/api/player_news?sort=-initial_published_date&page%5Blimit%5D=10&page%5Boffset%5D=0&filter%5Bteam-group%5D%5Bgroup%5D%5Bconjunction%5D=OR&filter%5Bprimary-team-filter%5D%5Bcondition%5D%5Bpath%5D=team.meta.drupal_internal__target_id&filter%5Bprimary-team-filter%5D%5Bcondition%5D%5Bvalue%5D={0}&filter%5Bprimary-team-filter%5D%5Bcondition%5D%5Boperator%5D==&filter%5Bprimary-team-filter%5D%5Bcondition%5D%5BmemberOf%5D=team-group&filter%5Brelated-team-filter%5D%5Bcondition%5D%5Bpath%5D=related_teams.meta.drupal_internal__target_id&filter%5Brelated-team-filter%5D%5Bcondition%5D%5Bvalue%5D={0}&filter%5Brelated-team-filter%5D%5Bcondition%5D%5Boperator%5D=IN&filter%5Brelated-team-filter%5D%5Bcondition%5D%5BmemberOf%5D=team-group&include=player,position,positions,team,team.secondary_logo,player.image,related_players,related_teams'.format(entity['id'])
    elif '/features/' in args['url']:
        entity = next((it for it in drupal_settings_json['rwEntity'] if it['type'] == 'league'), None)
        query = parse_qs(urlsplit(args['url']).query)
        if query.get('column'):
            api_url = 'https://www.nbcsportsedge.com/api/node/article?sort=-field_article_published_date&page%5Blimit%5D=15&page%5Boffset%5D=15&filter%5Bstatus%5D=1&include=field_article_hero_image,%20field_article_hero_image.thumbnail,%20field_article_author,%20field_article_column&filter%5Bfield_article_column.premium%5D%3C%3E1&filter%5Bfield_article_column.league.meta.drupal_internal__target_id%5D={}&filter%5Bfield_article_column.category%5D=matthew_berry'.format(entity['id'], query['column'][0])
        else:
            api_url = 'https://www.nbcsportsedge.com/api/node/article?sort=-field_article_published_date&page%5Blimit%5D=10&page%5Boffset%5D=0&filter%5Bstatus%5D=1&include=field_article_hero_image,%20field_article_hero_image.thumbnail,%20field_article_author,%20field_article_column&filter%5Bfield_article_column.premium%5D%3C%3E1&filter%5Bfield_article_column.league.meta.drupal_internal__target_id%5D={0}&filter%5Bor-group%5D%5Bgroup%5D%5Bconjunction%5D=OR&filter%5Bis-null-filter%5D%5Bcondition%5D%5Bpath%5D=field_article_column.category&filter%5Bis-null-filter%5D%5Bcondition%5D%5Boperator%5D=IS%20NULL&filter%5Bis-null-filter%5D%5Bcondition%5D%5BmemberOf%5D=or-group&filter%5Band-group%5D%5Bgroup%5D%5Bconjunction%5D=AND&filter%5Band-group%5D%5Bgroup%5D%5BmemberOf%5D=or-group&filter%5Bis-not-null-filter%5D%5Bcondition%5D%5Bpath%5D=field_article_column.category&filter%5Bis-not-null-filter%5D%5Bcondition%5D%5Boperator%5D=IS%20NOT%20NULL&filter%5Bis-not-null-filter%5D%5Bcondition%5D%5BmemberOf%5D=and-group&filter%5Bsportslanding-page-filter%5D%5Bcondition%5D%5Bpath%5D=field_article_column.sport_landing_page&filter%5Bsportslanding-page-filter%5D%5Bcondition%5D%5Bvalue%5D={0}&filter%5Bsportslanding-page-filter%5D%5Bcondition%5D%5BmemberOf%5D=and-group&filter%5Band-group-2%5D%5Bgroup%5D%5Bconjunction%5D=AND&filter%5Band-group-2%5D%5Bgroup%5D%5BmemberOf%5D=or-group&filter%5Bcategory-berry-filter%5D%5Bcondition%5D%5Bpath%5D=field_article_column.category&filter%5Bcategory-berry-filter%5D%5Bcondition%5D%5Bvalue%5D=matthew_berry&filter%5Bcategory-berry-filter%5D%5Bcondition%5D%5BmemberOf%5D=and-group-2'.format(entity['id'])
    else:
        entity = next((it for it in drupal_settings_json['rwEntity'] if it['type'] == 'league'), None)
        api_url = 'https://www.nbcsportsedge.com/api/player_news?page%5Blimit%5D=10&sort=-initial_published_date&include=team,league,league.sport&filter%5Bsport_headline%5D=1&filter%5Bleague.meta.drupal_internal__id%5D={}'.format(entity['id'])

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    n = 0
    feed_items = []
    for data in api_json['data']:
        if data['type'] == 'node--article':
            url = 'https://www.nbcsportsedge.com' + data['attributes']['path']['alias']
            if save_debug:
                logger.debug('getting content for ' + url)
            item = drupal.get_content(url, args, save_debug)
        elif data['type'] == 'player_news':
            item = get_item(data, args, save_debug)
        else:
            logger.warning('unhandled feed data type ' + data['type'])
            continue
        if item:
            if not item.get('url'):
                item['url'] = args['url']
                item['author'] = {"name": "NBC Sports EDGE"}
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if entity:
        feed['title'] = 'NBC Sports EDGE | ' + entity['label']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
