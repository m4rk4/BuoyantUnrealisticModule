import json
from urllib.parse import quote_plus

import utils

import logging

logger = logging.getLogger(__name__)


def get_feed(url, args, site_json, save_debug=False):
    trends_txt = utils.get_url_html('https://trends.google.com/trends/api/dailytrends?hl=en-US&tz=240&geo=US&hl=en-US&ns=15')
    if not trends_txt:
        return None
    n = trends_txt.find('{')
    trends_json = json.loads(trends_txt[n:])
    if save_debug:
        utils.write_file(trends_json, './debug/feed.json')

    feed_items = []
    for day in trends_json['default']['trendingSearchesDays']:
        for trend in day['trendingSearches']:
            item = None
            item_source = ''
            content_html = '<h3>{} searches</h3><ul>'.format(trend['formattedTraffic'])
            for article in trend['articles']:
                content_html += '<li><a href="{}">{}</a> &bull; {}</li>'.format(article['url'], article['title'], article['source'])
                if not item:
                    if save_debug:
                        logger.debug('trying to get content from ' + article['url'])
                    item_source = article['source']
                    item = utils.get_content(article['url'], {}, False)
            queries = []
            for query in trend['relatedQueries']:
                queries.append('<a href="https://trends.google.com{}">{}</a>'.format(query['exploreLink'], query['query']))
            content_html += '</ul><p>Related queries: {}</p><hr/>'.format(', '.join(queries))
            if item:
                content_html += '<h2><a href="{}">{}</a></h2>'.format(item['url'], item['title'])
                content_html += '<p>From {}<br/>By {}<br/>{}</p>'.format(item_source, item['author']['name'], item['_display_date'])
                item['content_html'] = content_html + item['content_html']
            else:
                item = {}
            item['id'] = '{}-{}'.format(day['date'], quote_plus(trend['title']['query']))
            item['url'] = trend['shareUrl']
            item['title'] = trend['title']['query']
            item['author'] = {"name": "Google Trends"}
            feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['title'] = 'Google Trends'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
