import html, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    clean_src = utils.clean_url(img_src)
    if 'images.radio.com' in clean_src:
        return '{}?width={}'.format(clean_src, width)
    return img_src


def get_content_type(content):
    if content.get('componentVariation'):
        return content['componentVariation']
    if content.get('_ref'):
        m = re.search(r'_components/([^/]+)/', content['_ref'])
        if m:
            return m.group(1)
    logger.warning('unable to determine content type for ' + content['_ref'])
    return ''


def render_content(content):
    content_html = ''
    content_type = get_content_type(content)

    if content_type == 'paragraph' or content_type == 'description':
        content_html += '<p>{}</p>'.format(content['text'])

    elif content_type == 'subheader':
        content_html += '<h3>{}</h3>'.format(content['text'])

    elif content_type == 'image' or content_type == 'feed-image':
        captions = []
        if content.get('caption'):
            captions.append(content['caption'])
        if content.get('credit'):
            captions.append(content['credit'])
        content_html += utils.add_image(resize_image(content['url']), ' | '.join(captions))

    elif content_type == 'youtube':
        content_html += utils.add_embed(content['origSource'])

    elif content_type == 'brightcove':
        content_html += utils.add_embed(content['seoEmbedUrl'])

    elif content_type == 'tweet':
        m = re.findall(r'(https:\/\/twitter\.com\/[^\/]+\/status/\d+)', content['html'])
        if m:
            content_html += utils.add_embed(m[-1])
        else:
            logger.warning('unable to determine tweet url')

    elif content_type == 'instagram-post':
        content_html += utils.add_embed(content['url'])

    elif content_type == 'omny':
        content_html += utils.add_embed(content['clipURL'])

    elif content_type == 'podcast-episode-listen':
        content_html += add_podcast(content['selectedPodcast']['podcastData']['podcastId'], content['selectedPodcast']['podcastData']['episodeId'])

    elif content_type == 'html-embed':
        soup = BeautifulSoup(content['text'], 'html.parser')
        if soup.iframe and soup.iframe.get('src'):
            content_html += utils.add_embed(soup.iframe['src'])
        elif soup.div and soup.div.get('class') and 'infogram-embed' in soup.div['class']:
            content_html += utils.add_embed('https://infogram.com/' + soup.div['data-id'])
        else:
            logger.warning('unhandled contentVariation html-embed')

    elif re.search(r'inline-related|station-livestream-listen', content_type):
        pass

    else:
        logger.warning('unhandled contentVariation ' + content_type)

    return content_html


def get_page_json(url):
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"99\", \"Microsoft Edge\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-amphora-page-json": "true",
    }
    return utils.get_url_json(utils.clean_url(url) + '?json', headers=headers)


def add_podcast(podcast_id, episode_id):
    if podcast_id:
        api_url = 'https://api.radio.com/v1/podcasts/{}'.format(podcast_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        url = 'https://www.audacy.com/podcasts/{}'.format(api_json['data']['attributes']['site_slug'])

    if episode_id:
        api_url = 'https://api.radio.com/v1/episodes/{}'.format(episode_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return ''
        url += '/{}'.format(api_json['data']['attributes']['site_slug'])

    item = get_podcast_content(url, {"embed":True}, False)
    if not item:
        return '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(url)
    return item['content_html']


def get_podcast_content(url, args, save_debug):
    page_json = get_page_json(url)
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    content_type = get_content_type(page_json['main'][0])
    if content_type == 'podcast-episode-page':
        episode_json = page_json['main'][0]['podcastEpisodeLead']['_computed']
        item['id'] = episode_json['episode']['id']
        item['url'] = 'https://www.audacy.com/podcasts/{}/{}'.format(episode_json['podcast']['site_slug'], episode_json['episode']['site_slug'])
        item['title'] = episode_json['title']
        dt = datetime.fromisoformat(episode_json['episode']['published_date'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['author'] = {}
        item['author']['name'] = episode_json['podcast']['title']
        item['author']['url'] = 'https://www.audacy.com/podcasts/' + episode_json['podcast']['site_slug']
        item['tags'] = [episode_json['category']]
        item['summary'] = episode_json['description']
        item['_image'] = episode_json['imageURL']
        item['_audio'] = episode_json['episode']['audio_url']
        item['_duration'] = episode_json['duration_seconds_formatted']
        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small><a href="{}">{}</a><br/>{} &#8226; {}<br/>{}</small>'.format(item['url'], item['title'], item['author']['url'], item['author']['name'], utils.format_display_date(dt, False), item['_duration'], item['tags'][0])
        item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(item['_audio'], poster, desc)
        if not 'embed' in args:
            item['content_html'] += '<div>{}</div>'.format(item['summary'].replace('\n', '<br/>'))

    elif content_type == 'podcast-show-page':
        podcast_json = page_json['main'][0]['podcastLead']['_computed']
        item['id'] = podcast_json['podcast']['id']
        item['url'] = 'https://www.audacy.com/podcasts/' + podcast_json['podcast']['site_slug']
        item['title'] = podcast_json['title']
        item['author'] = {}
        item['author']['name'] = item['title']
        item['author']['url'] = item['url']
        item['tags'] = [podcast_json['category']]
        item['summary'] = podcast_json['description']
        item['_image'] = podcast_json['imageURL']

        poster = '{}/image?url={}&height=128'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>Category: {}</small>'.format(item['url'], item['title'], item['tags'][0])
        item['content_html'] = '<div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div></div>'.format(poster, desc)
        item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><h4 style="margin-top:0; margin-bottom:1em;">Episodes:</h4>'

        if 'embed' in args:
            n = 5
        else:
            n = 10
        for i, episode in enumerate(page_json['main'][0]['episodeList']['_computed']['episodes']):
            if i == n:
                break
            dt = datetime.fromisoformat(episode['attributes']['published_date'].replace('Z', '+00:00'))
            if not item.get('_timestamp'):
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt)
            elif item['_timestamp'] < dt.timestamp():
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt)

            poster = '{}/static/play_button-48x48.png'.format(config.server)
            desc = '<h5 style="margin-top:0; margin-bottom:0;"><a href="https://www.audacy.com{}">{}</a></h5><small>{} &#8226; {}</small>'.format(episode['attributes']['episode_detail_url'], episode['attributes']['title'], utils.format_display_date(dt, False), episode['attributes']['duration_seconds_formatted'])
            item['content_html'] += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(episode['attributes']['audio_url'], poster, desc)
        item['content_html'] += '</blockquote>'
        if not 'embed' in args:
            item['content_html'] += '<div>{}</div>'.format(item['summary'].replace('\n', '<br/>'))
    return item

def get_content(url, args, save_debug=False):
    if '/podcasts/' in url:
        return get_podcast_content(url, args, save_debug)

    page_json = get_page_json(url)
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    article_json = page_json['main'][0]

    item = {}
    item['id'] = article_json['_ref']
    item['url'] = article_json['canonicalUrl'].replace('http:', 'https:')
    item['title'] = article_json['headline']

    if article_json.get('firstPublishedDate'):
        dt = datetime.fromisoformat(article_json['firstPublishedDate'].replace('Z', '+00:00'))
    else:
        dt = datetime.fromisoformat(article_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags') and article_json['tags'].get('textTags'):
        item['tags'] = article_json['tags']['textTags'].copy()

    if article_json.get('feedImg'):
        item['_image'] = article_json['feedImg']['url']
    elif article_json.get('feedImgUrl'):
        item['_image'] = article_json['feedImgUrl']

    item['summary'] = article_json['pageDescription']

    item['content_html'] = ''
    if article_json.get('lead'):
        if  get_content_type(article_json['lead'][0]) == 'omny':
            if article_json.get('feedImg'):
                item['content_html'] += render_content(article_json['feedImg']) + '<br/>'
            elif article_json.get('feedImgUrl'):
                item['content_html'] += utils.add_image(article_json['feedImgUrl']) + '<br/>'
        for content in article_json['lead']:
            item['content_html'] += render_content(content)

    for content in article_json['content']:
        item['content_html'] += render_content(content)

    if article_json.get('slides'):
        for slide in article_json['slides']:
            item['content_html'] += '<h2>{}</h2>'.format(slide['title'].replace('<br />', ''))
            for content in slide['slideEmbed']:
                item['content_html'] += render_content(content)
            for content in slide['description']:
                item['content_html'] += render_content(content)

    return item


def get_feed(args, save_debug=False):
    page_json = get_page_json(args['url'])
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    content_type = get_content_type(page_json['main'][0])
    if content_type == 'section-front' or content_type == 'station-front':
        main_content = page_json['main'][0]['mainContent']
    elif content_type == 'topic-page':
        main_content = []
        main_content.append(page_json['main'][0]['twoColumnComponent'])
    else:
        logger.warning('unhandled feed page type {} in {}'.format(content_type, args['url']))
        return None

    articles = []
    for content in main_content:
        content_type = get_content_type(content)
        if content_type == 'multi-column' or content_type == 'two-column-component' or content_type == 'latest-content':
            for key, val in content.items():
                if re.search(r'col\d|(first|second|third)Column', key):
                    for column in val:
                        if column['_computed'].get('articles'):
                            for article in column['_computed']['articles']:
                                articles.append(article)
                        if column['_computed'].get('content'):
                            for article in column['_computed']['content']:
                                articles.append(article)

    n = 0
    items = []
    for article in articles:
        if save_debug:
            logger.debug('getting contents for ' + article['canonicalUrl'])
        item = get_content(article['canonicalUrl'], args, save_debug)
        if item:
            if '/topic/' not in args['url'] and not item['url'].startswith(args['url'].lower()):
                continue
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
            else:
                logger.debug('skipping ' + item['url'])

    feed = utils.init_jsonfeed(args)
    if page_json['main'][0]['_computed'].get('isStation'):
        title = page_json['main'][0]['stationName']
    else:
        title = 'Audacy'
    if page_json['main'][0].get('title'):
        if title:
            title += ' > '
        title += page_json['main'][0]['title'].title()
    elif page_json.get('pageHeader') and page_json['pageHeader'][0].get('plaintextPrimaryHeadline'):
        if title:
            title += ' > '
        title += page_json['pageHeader'][0]['plaintextPrimaryHeadline']
    feed['title'] = title
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed