import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
        query = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'
        query = '?slug=' + '&slug='.join(paths)

    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if next_data['pageProps'].get('__N_REDIRECT'):
        return get_content('https://hackernoon' + next_data['pageProps']['__N_REDIRECT'], args, site_json, save_debug)

    article_json = next_data['pageProps']['data']
    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(article_json['publishedAt'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_json['profile']['displayName']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = article_json['tags'].copy()

    item['content_html'] = ''
    if article_json.get('tldr'):
        item['summary'] = article_json['tldr']
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'
    elif article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if article_json.get('mainImage'):
        item['image'] = article_json['mainImage']
        item['content_html'] += utils.add_image(article_json['mainImage'])

    if article_json.get('audioData'):
        item['content_html'] += utils.add_audio(article_json['audioData'][0]['url'], '', 'Read by ' + article_json['audioData'][0]['nickname'], '', '', '', '', 0, 'audio/mpeg', show_poster=False, use_video_js=True)

    if article_json.get('parsed'):
        soup = BeautifulSoup(article_json['parsed'], 'html.parser')
        for el in soup.select('p:has(> img)'):
            new_html = utils.add_image(el.img['src'], el.img.get('alt'))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in soup.find_all('pre', recursive=False):
            el.attrs = {}
            el['style'] = 'width:100%; padding:0.5em; white-space:pre; overflow-x:scroll; background-color:light-dark(#ddd,#333);'

        for el in soup.find_all(class_='notice'):
            el.attrs = {}
            el['style'] = "margin:1em 0; padding:2px 1em; border-radius:10px; background-color:rgb(245,190,49);"

        item['content_html'] += str(soup)

    return item


def get_feed(url, args, site_json, save_debug):
    # Only https://hackernoon.com/feed
    if args['url'].endswith('/feed'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    params = parse_qs(split_url.query)

    n = 0
    feed_items = []
    feed_title = ''

    if 'c' in paths:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        feed_title = next_data['pageProps']['parentCategoryData']['title'] + ' | HackerNoon'
        for tag in next_data['pageProps']['parentCategoryData']['topTags']:
            for story in tag['stories']:
                if 'slug' not in story:
                    continue
                story_url = 'https://hackernoon.com/' + story['slug']
                if save_debug:
                    logger.debug('getting content from ' + story_url)
                item = get_content(story_url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
    elif 'tagged' in paths:
        i = paths.index('tagged')
        tag = paths[i + 1]
        feed_title = '#' + tag + ' Stories | HackerNoon'
        query_url = 'https://{}-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(4.24.0)%3B%20Browser%20(lite)%3B%20JS%20Helper%20(3.14.0)%3B%20react%20(17.0.2)%3B%20react-instantsearch%20(6.40.4)&x-algolia-api-key={}&x-algolia-application-id={}'.format(site_json['x-algolia-application-id'], site_json['x-algolia-api-key'], site_json['x-algolia-application-id'].upper())
        query = '{"requests":[{"indexName":"stories_publishedAt","params":"clickAnalytics=true&facetFilters=%5B%22tags%3A' + tag + '%22%5D&facets=%5B%22tags%22%5D&highlightPostTag=%3C%2Fais-highlight-0000000000%3E&highlightPreTag=%3Cais-highlight-0000000000%3E&hitsPerPage=13&maxValuesPerFacet=10&page=0&query=&tagFilters="}]}'
        query_json = utils.post_url(query_url, data=query)
        if not query_json:
            return None
        if save_debug:
            utils.write_file(query_json, './debug/feed.json')
        for story in query_json['results'][0]['hits']:
            if 'slug' not in story:
                continue
            story_url = 'https://hackernoon.com/' + story['slug']
            if save_debug:
                logger.debug('getting content from ' + story_url)
            item = get_content(story_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    elif 'u' in paths:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/next.json')
        feed_title = next_data['pageProps']['data']['profile']['displayName'] + ' | HackerNoon'
        api_url = 'https://api.hackernoon.com/p/hackernoonMongo2/profiles/stories?id={}&page=0&sort=latest'.format(next_data['pageProps']['data']['profile']['id'])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for story in api_json['data']:
            if 'slug' not in story:
                continue
            story_url = 'https://hackernoon.com/' + story['slug']
            if save_debug:
                logger.debug('getting content from ' + story_url)
            item = get_content(story_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    elif 'latest' in paths or 'techbeat' in paths:
        stories_url = ''
        if 'latest' in paths:
            stories_url = 'https://us-central1-hackernoon-app.cloudfunctions.net/app/trending-stories?type=latest'
            feed_title = 'Latest Stories | HackerNoon'
        elif 'techbeat' in paths:
            stories_url = 'https://us-central1-hackernoon-app.cloudfunctions.net/app/trending-stories'
            if params and 'filter' in params:
                stories_url += '?type=' + params['filter'][0]
                feed_title = 'Stories Ranked by ' + params['filter'][0].title() + ' | HackerNoon'
            else:
                stories_url += '?type=trending'
                feed_title = 'Stories Ranked by Reads | HackerNoon'
        stories_json = utils.get_url_json(stories_url)
        if not stories_json:
            return None
        if save_debug:
            utils.write_file(stories_json, './debug/feed.json')
        for story in stories_json['stories']:
            story_url = 'https://hackernoon.com/' + story['slug']
            if save_debug:
                logger.debug('getting content from ' + story_url)
            item = get_content(story_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed