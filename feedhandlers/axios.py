import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def add_image(image):
    if image.get('crops'):
        if image['crops']['16x9'].get('videos'):
            img_src = image['crops']['16x9']['url']
        else:
            img = utils.closest_dict(image['crops']['16x9']['sizes'], 'width', 1000)
            img_src = img['url']
    else:
        logger.warning('unknown image src ' + str(image))
        return ''
    if image.get('caption'):
        caption = format_blocks(image['caption'])
        if caption.startswith('<p>'):
            caption = caption.replace('<p>', '')
            caption = caption.replace('</p>', '<br/><br/>')
            if caption.endswith('<br/><br/>'):
                caption = caption[:-10]
    else:
        caption = ''
    return utils.add_image(img_src, caption)


def format_styles(block, entities):
    ranges = []
    if block.get('inlineStyleRanges'):
        for rng in block['inlineStyleRanges']:
            if rng['style'] == 'BOLD':
                rng['tag'] = '<b>'
                ranges.append(rng.copy())
                rng['tag'] = '</b>'
                rng['offset'] += rng['length']
                ranges.append(rng.copy())
            elif rng['style'] == 'ITALIC':
                rng['tag'] = '<i>'
                ranges.append(rng.copy())
                rng['tag'] = '</i>'
                rng['offset'] += rng['length']
                ranges.append(rng.copy())
            else:
                logger.warning('unhandled style type ' + rng['style'])
                continue
    if block.get('entityRanges'):
        for rng in block['entityRanges']:
            if isinstance(entities, list):
                entity = entities[rng['key']]
            elif isinstance(entities, dict):
                entity = entities[str(rng['key'])]
            if entity['type'] == 'LINK':
                if entity['data'].get('href'):
                    href = entity['data']['href']
                else:
                    href = entity['data']['url']
                if 'link.axios.com' in href:
                    href = utils.get_redirect_url(href)
                rng['tag'] = '<a href="{}">'.format(href)
                ranges.append(rng.copy())
                rng['tag'] = '</a>'
                rng['offset'] += rng['length']
                ranges.append(rng.copy())
            else:
                logger.warning('unhandled entity type ' + entity['type'])
                continue
    ranges = sorted(ranges, key=lambda x: x['offset'])
    x = 0
    text = ''
    for rng in ranges:
        text += block['text'][x:rng['offset']] + rng['tag']
        x = rng['offset']
    text += block['text'][x:]
    return text


def format_blocks(blocks):
    content_html = ''
    entities = blocks['entityMap']
    for i, block in enumerate(blocks['blocks']):
        if block['type'] == 'unstyled':
            content_html += '<p>{}</p>'.format(format_styles(block, entities))

        elif block['type'] == 'header-two':
            content_html += '<h2>{}</h2>'.format(format_styles(block, entities))

        elif block['type'] == 'blockquote':
            content_html += utils.add_blockquote(format_styles(block, entities))

        elif block['type'] == 'plain-quote':
            quote = format_styles(block, entities)
            author = ''
            try:
                next_block = blocks['blocks'][i+1]
                if next_block['type'] == 'quote-attribution':
                    author = format_styles(next_block, entities)
            except:
                pass
            content_html += utils.add_pullquote(quote, author)

        elif block['type'] == 'quote-attribution':
            pass

        elif re.search(r'ordered-list-item', block['type']):
            if block['type'] == 'unordered-list-item':
                tag = 'ul'
            else:
                tag = 'ol'
            try:
                prev_block = blocks['blocks'][i-1]
                if not re.search(r'ordered-list-item', prev_block['type']):
                    content_html += '<{}>'.format(tag)
            except:
                # must be the first block
                content_html += '<{}>'.format(tag)
            content_html += '<li>{}</li>'.format(format_styles(block, entities))
            try:
                next_block = blocks['blocks'][i+1]
                if not re.search(r'ordered-list-item', next_block['type']):
                    content_html += '</{}>'.format(tag)
            except:
                # must be the last block
                content_html += '</{}>'.format(tag)

        elif block['type'] == 'image':
            caption = format_styles(block, entities)
            content_html += utils.add_image(block['data']['src'], caption)

        elif block['type'] == 'embed':
            if block['data']['type'] == 'twitter' or block['data']['type'] == 'youtube' or block['data']['type'] == 'giphy':
                content_html += utils.add_embed(block['data']['url'])

            elif block['data']['type'] == 'axios-visual' or block['data']['type'] == 'datawrapper':
                content_html += utils.add_image(block['data']['oembed']['apple_fallback'], block['text'], link=block['data']['url'])

            elif block['data']['type'] == 'megaphone':
                content_html += utils.add_embed('https://playlist.megaphone.fm/?e=' + block['data']['oembed']['episode_id'])

            elif block['data']['type'] == 'jwplayer-video':
                content_html += utils.add_embed(block['data']['url'])

            elif block['data']['type'] == 'documentcloud-document':
                content_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(block['data']['url'])

            else:
                logger.warning('unhandled embed type ' + block['data']['type'])

        elif block['type'] == 'keep-reading':
            pass

        else:
            logger.warning('unhandled block type ' + block['type'])
    return content_html


def get_item(content_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['permalink']

    if content_json.get('headline'):
        item['title'] = content_json['headline']
    elif content_json.get('subject_line'):
        item['title'] = content_json['subject_line']
    elif content_json.get('subjectLine'):
        item['title'] = content_json['subjectLine']

    if content_json.get('published_date'):
        dt = datetime.fromisoformat(content_json['published_date'])
    elif content_json.get('publishedDate'):
        dt = datetime.fromisoformat(content_json['publishedDate'])
    else:
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('last_published'):
        dt = datetime.fromisoformat(content_json['last_published'])
        item['date_modified'] = dt.isoformat()
    elif content_json.get('last_updated'):
        dt = datetime.fromisoformat(content_json['last_updated'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = ''
    authors = []
    for author in content_json['authors']:
        if author.get('display_name'):
            authors.append(author['display_name'])
        elif author.get('displayName'):
            authors.append(author['displayName'])
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if content_json.get('editors'):
        authors = []
        for author in content_json['editors']:
            if author.get('display_name'):
                authors.append(author['display_name'])
            elif author.get('displayName'):
                authors.append(author['displayName'])
        item['author']['name'] += ' (Edited by ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)) + ')'

    item['tags'] = []
    if content_json.get('primary_tag'):
        item['tags'].append(content_json['primary_tag']['name'])
    if content_json.get('tags'):
        for tag in content_json['tags']:
            item['tags'].append(tag['name'])
    if content_json.get('topics'):
        for tag in content_json['topics']:
            item['tags'].append(tag['name'])
    if content_json.get('subtopics'):
        for tag in content_json['subtopics']:
            item['tags'].append(tag['name'])

    if content_json.get('summary'):
        soup = BeautifulSoup(content_json['summary'], 'html.parser')
        for el in soup.find_all('a'):
            href = el['href']
            if 'link.axios.com' in href:
                href = utils.get_redirect_url(href)
            el.attrs = {}
            el['href'] = href
        item['summary'] = str(soup)
    elif content_json.get('preview_text'):
        item['summary'] = content_json['preview_text']

    item['content_html'] = ''
    if content_json.get('primary_image'):
        if content_json['primary_image'].get('base_image_url'):
            item['_image'] = content_json['primary_image']['base_image_url']
        elif content_json['primary_image'].get('baseImageUrl'):
            item['_image'] = content_json['primary_image']['baseImageUrl']
        if not content_json.get('subscription'):
            # Newsletters don't get a lede photo
            item['content_html'] += add_image(content_json['primary_image'])
    elif content_json.get('social_image'):
        item['_image'] = content_json['social_image']['base_image_url']

    if content_json.get('intro'):
        item['content_html'] += format_blocks(content_json['intro']) + '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
    elif content_json.get('introHtml'):
        item['content_html'] += content_json['introHtml'] + '<div>&nbsp;</div><hr/><div>&nbsp;</div>'

    if content_json.get('blocks'):
        item['content_html'] += format_blocks(content_json['blocks'])

    if content_json.get('chunks'):
        for chunk in content_json['chunks']:
            item['content_html'] += '<h3>{}</h3>'.format(chunk['headline'])
            if chunk.get('primary_image') and chunk['primary_image'].get('id'):
                item['content_html'] += add_image(chunk['primary_image'])
            item['content_html'] += format_blocks(chunk['blocks'])
            item['content_html'] += '<hr/>'

    if content_json.get('outro'):
        item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>' + format_blocks(content_json['outro'])
    elif content_json.get('outroHtml'):
        item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>' + content_json['outroHtml']

    return item


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    query = ''
    if 'local' in paths:
        if len(paths) == 6:
            query = '?audienceSlug={}&yearOrSection={}&month={}&day={}&slug={}'.format(paths[1], paths[2], paths[3], paths[4], paths[5])
        else:
            query = '?audienceSlug={}'.format(paths[1])
    elif len(paths) == 4:
        query = '?year={}&month={}&day={}&slug={}'.format(paths[0], paths[1], paths[2], paths[3])
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    # print(next_url)
    next_data = utils.get_url_json(next_url, site_json=site_json)
    if not next_data:
        #logger.debug('scraper error {} - getting NEXT_DATA from {}'.format(r.status_code, url))
        page_html = utils.get_url_html(url, site_json=site_json)
        if not page_html:
            page_html = utils.get_url_html(url, user_agent='googlecache')
            if not page_html:
                return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                logger.debug('updating {} buildId'.format(split_url.netloc))
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    if next_data['pageProps']['pageType'] == 'story':
        if next_data['pageProps'].get('audience'):
            return get_item(next_data['pageProps']['data']['story'], args, site_json, save_debug)
        else:
            return get_item(next_data['pageProps']['pageProps']['data']['story'], args, site_json, save_debug)
    elif next_data['pageProps']['pageType'] == 'newsletter':
        return get_item(next_data['pageProps']['data']['newsletter'], args, site_json, save_debug)
    else:
        logger.warning('unknown pageType {} for {}'.format(next_data['pageProps']['pageType'], url))
        return None

    split_url = urlsplit(url)
    content_id = ''
    m = re.search(r'([a-f0-9]+-[a-f0-9]+-[a-f0-9]+-[a-f0-9]+-[a-f0-9]+)\.html', split_url.path)
    if m:
        content_id = m.group(1)
    else:
        if '/local/' in split_url.path:
            m = re.search('/local/(.*)', split_url.path)
            content_id = m.group(1)
    if content_id:
        if '/newsletters/' in split_url.path:
            api_url = 'https://api.axios.com/api/render/newsletters/{}/'.format(content_id)
        elif 'local' in split_url.path:
            api_url = 'https://api.axios.com/api/render/audience-content/{}'.format(content_id)
        else:
            #api_url = 'https://www.axios.com/api/axios-web/get-story/by-id/{}'.format(content_id)
            api_url = 'https://api.axios.com/api/render/content/{}/'.format(content_id)
        content_json = utils.get_url_json(api_url)
        if not content_json:
            return None
    else:
        if '/newsletters/' in split_url.path:
            page_html = utils.get_url_html(url)
            soup = BeautifulSoup(page_html, 'html.parser')
            el = soup.find('script', id='__NEXT_DATA__')
            if not el:
                logger.warning('unable to find NEXT_DATA in ' + url)
                return None
            next_data = json.loads(el.string)
            content_json = next_data['props']['pageProps']['data']['newsletter']
        else:
            logger.warning('unable to determine content id for ' + url)
            return None
    return get_item(content_json, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    # Author feed: https://api.axios.com/api/render/stream/content/?author_username=mikeallen
    # Topic feed: https://api.axios.com/api/render/stream/content/?topic_slug=technology
    # All newsletters for the month: https://api.axios.com/api/render/newsletters/?audience_slug=national&year=2022&month=02
    if split_url.netloc == 'api.axios.com' and 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    stories = []
    if next_data['pageProps'].get('pageType'):
        if next_data['pageProps']['pageType'] == 'homepage':
            for key, val in next_data['pageProps']['data']['homepageData'].items():
                if isinstance(val, list):
                    stories += val.copy()
        elif next_data['pageProps']['pageType'] == 'topic':
            stories = next_data['pageProps']['data']['topicStories']
        elif next_data['pageProps']['pageType'] == 'subtopic':
            stories = next_data['pageProps']['data']['subtopicStories']
        elif next_data['pageProps']['pageType'] == 'section':
            for key, val in next_data['pageProps']['data']['initialStreamContent']['storyMap'].items():
                stories.append(val)
        elif next_data['pageProps']['pageType'] == 'author':
            for key, val in next_data['pageProps']['data']['initialStoryStreamContent']['storyMap'].items():
                stories.append(val)
        elif next_data['pageProps']['pageType'] == 'newsletter':
            for author in next_data['pageProps']['data']['subscription']['primary_contributors']:
                newsletters = utils.get_url_json('https://api.axios.com/api/render/stream/newsletters/?page=1&page_size=10&author_id={}'.format(author['id']))
                if newsletters:
                    for it in newsletters['results']:
                        story = utils.get_url_json('https://api.axios.com/api/render/newsletters/{}'.format(it))
                        if story['subscription']['slug'] == next_data['pageProps']['data']['subscription']['slug']:
                            stories.append(story)
            if not stories:
                stories.append(next_data['pageProps']['data']['newsletter'])
        else:
            logger.warning('unhandled pageType {} for {}'.format(next_data['pageProps']['pageType'], url))
            return None
    elif next_data['pageProps'].get('audience'):
        if next_data['pageProps']['data']['pageType'] == 'homepage':
            for key, val in next_data['pageProps']['data'].items():
                if isinstance(val, dict):
                    if val.get('content'):
                        stories += val['content'].copy()
                elif isinstance(val, list):
                    for it in val:
                        if it.get('content'):
                            stories += it['content'].copy()

    n = 0
    feed_items = []
    for story in stories:
        if 'local' in paths:
            if not re.search(r'/{}/'.format(paths[1]), story['permalink']):
                continue
        if save_debug:
            logger.debug('getting content for ' + story['permalink'])
        if story.get('blocks'):
            item = get_item(story, args, site_json, save_debug)
        else:
            item = get_content(story['permalink'], args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
