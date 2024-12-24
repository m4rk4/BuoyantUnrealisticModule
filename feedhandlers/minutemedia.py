import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    return 'https://images2.minutemediacdn.com/image/upload/c_fill,w_{},f_auto,q_auto,g_auto/{}'.format(width, quote_plus(img_src))


def get_content(url, args, site_json, save_debug=False):
    # All sites: https://fansided.com/network/
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_id = paths[-1].split('-')[-1]
    article_json = None
    if re.search(r'\d', post_id):
        api_url = 'https://{}/api/properties/{}/posts?ids={}&limit=1&withBody=true'.format(split_url.netloc, site_json['site_property'], post_id)
        # print(api_url)
        api_json = utils.get_url_json(api_url)
        if api_json and api_json.get('data') and api_json['data'].get('articles'):
            article_json = api_json['data']['articles'][0]
    if not article_json:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', string=re.compile('__PRELOADED_STATE__'))
        if el:
            i = el.string.find('{')
            j = el.string.rfind('}') + 1
            preloaded_state = json.loads(el.string[i:j])
            article_json = preloaded_state['template']
        else:
            # Seems to be specific to mentalfloss.com
            el = soup.find('script', attrs={"type": "qwik/json"})
            if el:
                qwik_json = json.loads(el.string)
                # TODO: how to determine valid ids?
                ids = [x for x in qwik_json['objs'] if isinstance(x, str) and x.startswith('01')]
                if ids:
                    post_id = ','.join(ids)
                    api_url = 'https://{}/api/properties/{}/posts?ids={}&limit=1&withBody=true'.format(split_url.netloc, site_json['site_property'], post_id)
                    api_json = utils.get_url_json(api_url)
                    if api_json and api_json.get('data') and api_json['data'].get('articles'):
                        article_json = api_json['data']['articles'][0]
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    if article_json.get('id'):
        item['id'] = article_json['id']
    elif article_json.get('articleId'):
        item['id'] = article_json['articleId']

    if article_json.get('articleUrl'):
        item['url'] = article_json['articleUrl']
    else:
        item['url'] = url

    try:
        item['title'] = article_json['title'].encode('iso-8859-1').decode('utf-8')
    except:
        item['title'] = article_json['title']

    if article_json.get('createdAtISO'):
        dt = datetime.fromisoformat(article_json['createdAtISO'])
    elif article_json.get('createdAt'):
        dt = datetime.fromisoformat(article_json['createdAt'])
    else:
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('updatedAtISO'):
        dt = datetime.fromisoformat(article_json['updatedAtISO'])
    elif article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'])
    else:
        dt = None
    if dt:
        item['date_modified'] = dt.isoformat()

    if article_json.get('authors'):
        item['author'] = {}
        if isinstance(article_json['authors'], list):
            authors = []
            for it in article_json['authors']:
                authors.append(it['name'])
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            item['author']['name'] = article_json['authors']['owner']['name']
            # TODO: co-authors?

    item['tags'] = article_json['tags'].copy()

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    item['content_html'] = ''
    if article_json.get('intro'):
        try:
            item['content_html'] += '<p><em>' + article_json['intro'].encode('iso-8859-1').decode('utf-8') + '</em></p>'
        except:
            item['content_html'] += '<p><em>' + article_json['intro'] + '</em></p>'

    if article_json.get('cover')  and article_json['cover'].get('image'):
        captions = []
        if article_json['cover']['image'].get('path'):
            item['_image'] = resize_image(article_json['cover']['image']['path'])
            if article_json['cover']['image'].get('caption'):
                captions.append(article_json['cover']['image']['caption'])
            if article_json['cover']['image'].get('credit'):
                captions.append(article_json['cover']['image']['credit'])
        elif article_json['cover']['image'].get('value'):
            item['_image'] = resize_image(article_json['cover']['image']['value']['path'])
            if article_json['cover']['image']['value'].get('caption'):
                captions.append(article_json['cover']['image']['value']['caption'])
            if article_json['cover']['image']['value'].get('credit'):
                captions.append(article_json['cover']['image']['value']['credit'])
        for i, it in enumerate(captions):
            try:
                captions[i] = it.encode('iso-8859-1').decode('utf-8')
            except:
                pass
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for content in article_json['body']:
        if content['type'] == 'inline-text':
            if content.get('value'):
                try:
                    item['content_html'] += content['value']['html'].encode('iso-8859-1').decode('utf-8')
                except:
                    item['content_html'] += content['value']['html']
            elif content.get('html'):
                try:
                    item['content_html'] += content['html'].encode('iso-8859-1').decode('utf-8')
                except:
                    item['content_html'] += content['html']
        elif content['type'] == 'image':
            captions = []
            if content.get('image'):
                image = content['image']
            elif content.get('value'):
                image = content['value']
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('credit'):
                captions.append(image['credit'])
            for i, it in enumerate(captions):
                try:
                    captions[i] = it.encode('iso-8859-1').decode('utf-8')
                except:
                    pass
            item['content_html'] += utils.add_image(resize_image(image['path']), ' | '.join(captions))
        elif content['type'] == 'twitter':
            if content.get('value'):
                item['content_html'] += utils.add_embed(content['value']['originalEmbedUrl'])
            elif content.get('mediaId'):
                item['content_html'] += utils.add_embed('https://twitter.com/__/status/' + content['mediaId'])
            else:
                logger.warning('unhandled twitter content in ' + item['url'])
        elif content['type'] == 'youtube':
            if content.get('value'):
                item['content_html'] += utils.add_embed(content['value']['originalEmbedUrl'])
            elif content.get('mediaId'):
                item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + content['mediaId'])
            else:
                logger.warning('unhandled youtube content in ' + item['url'])
        elif content['type'] == 'quote':
            if content.get('value'):
                item['content_html'] += utils.add_pullquote(content['value']['text'], content['value']['cite'])
            else:
                logger.warning('unhandled quote content in ' + item['url'])
        elif content['type'] == 'iframeEmbed':
            src = ''
            if content.get('value'):
                src = content['value']['src']
            elif content.get('src'):
                src = content['src']
            if src:
                if 'tallysight.com' not in src:
                    item['content_html'] += utils.add_embed(src)
            else:
                logger.warning('unhandled iframeEmbed content in ' + item['url'])
        elif content['type'] == 'mm-content-embed':
            embed_soup = None
            if content.get('value'):
                embed_soup = BeautifulSoup(content['value']['html'], 'html.parser')
            elif content.get('html'):
                embed_soup = BeautifulSoup(content['html'], 'html.parser')
            if embed_soup:
                if embed_soup.blockquote['data-type'] == 'GroupOfLinks':
                    embed_json = utils.get_url_json(embed_soup.blockquote['data-url'])
                    # utils.write_file(embed_json, './debug/embed.json')
                    if embed_json and embed_json.get('data') and embed_json['data'].get('posts'):
                        item['content_html'] += '<ul>'
                        for it in embed_json['data']['posts']:
                            item['content_html'] += '<li><a href="{}">{}</a></li>'.format(it['url'], it['title'])
                        item['content_html'] += '</ul>'
                    else:
                        logger.warning('unhandled mm-content-embed GroupOfLinks in ' + item['url'])
                elif embed_soup.blockquote['data-type'] == 'Rank':
                    item['content_html'] += '<table style="width:100%; border-top:2px solid #ccc; padding:8px;"><tr><td style="width:56px;"><span style="font-size:4em; font-weight:bold;">{}</span></td><td><div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(embed_soup.blockquote['data-rank'], embed_soup.blockquote['data-player-name'])
                    if embed_soup.blockquote.get('data-meta-a'):
                        item['content_html'] += '<div>{}</div>'.format(embed_soup.blockquote['data-meta-a'])
                    if embed_soup.blockquote.get('data-meta-b'):
                        item['content_html'] += '<div>{}</div>'.format(embed_soup.blockquote['data-meta-b'])
                    item['content_html'] += '</td>'
                    if embed_soup.blockquote.get('data-team'):
                        embed_json = json.loads(html.unescape(embed_soup.blockquote['data-team']))
                        if embed_json.get('logoUrl'):
                            item['content_html'] += '<td style="width:56px;"><img src="{}" style="width:100%;"/></td>'.format(embed_json['logoUrl'])
                    item['content_html'] += '</tr></table>'
                elif embed_soup.blockquote['data-type'] == 'Trade':
                    embed_json = json.loads(html.unescape(embed_soup.blockquote['data-teams']))
                    if len(embed_json) == 2:
                        item['content_html'] += '<table style="width:100%; border-top:2px solid #ccc; padding:8px;"><tr>'
                        item['content_html'] += '<td style="width:56px;"><img src="{}" style="width:100%;"/></td><td><div style="font-size:1.2em; font-weight:bold;">{}</div></td>'.format(embed_json[0]['logoUrl'], embed_json[0]['name'])
                        item['content_html'] += '<td></td>'
                        item['content_html'] += '<td><div style="font-size:1.2em; font-weight:bold; text-align:right;">{}</div></td><td style="width:56px;"><img src="{}" style="width:100%;"/></td></tr>'.format(embed_json[1]['name'], embed_json[1]['logoUrl'])
                        embed_json = json.loads(html.unescape(embed_soup.blockquote['data-team-gets']))
                        item['content_html'] += '<tr><td colspan="2" style="vertical-align:top;">Receive'
                        for it in embed_json[0]:
                            item['content_html'] += '<br/><b>{}</b>'.format(it)
                        item['content_html'] += '</td><td><span style="font-size:3em; font-weight:bold; text-align:center;">⇄</span></td><td colspan="2" style="vertical-align:top;"><div style="text-align:right;">Receive'
                        for it in embed_json[1]:
                            item['content_html'] += '<br/><b>{}</b>'.format(it)
                        item['content_html'] += '</div></td></tr></table>'
                    else:
                        logger.warning('unhandled mm-content-embed Rank with >2 teams in ' + item['url'])
                elif embed_soup.blockquote['data-type'] == 'StoryLink' and (embed_soup.blockquote['data-call-to-action'] == 'Next' or embed_soup.blockquote['data-call-to-action'] == 'Subscribe'):
                    pass
                else:
                    logger.warning('unhandled mm-content-embed data-type {} in {}'.format(embed_soup.blockquote['data-type'], item['url']))
            else:
                logger.warning('unhandled mm-content-embed in ' + item['url'])
        elif content['type'] == 'table':
            item['content_html'] += '<table style="width:100%; border-collapse:collapse;">'
            for i, tr in enumerate(content['data']):
                if i % 2 == 0:
                    item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black; background-color:#ccc;">'
                else:
                    item['content_html'] += '<tr style="line-height:2em; border-bottom:1pt solid black;">'
                for td in tr:
                    item['content_html'] += '<td style="padding:0 8px 0 8px;">' + re.sub(r'^<p>(.*?)</p>$', r'\1', td.strip().encode('iso-8859-1').decode('utf-8')) + '</td>'
                item['content_html'] += '</tr>'
            item['content_html'] += '</table>'
        elif content['type'] == 'divider':
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        elif content['type'] == 'relatedTopics' or content['type'] == 'table-of-contents':
            continue
        else:
            logger.warning('unhandled body content type {} in {}'.format(content['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile('__PRELOADED_STATE__'))
    if not el:
        logger.warning('unable to find __PRELOADED_STATE__ in ' + url)
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    preloaded_state = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(preloaded_state, './debug/feed.json')

    api_json = None
    for key, val in preloaded_state['template'].items():
        if isinstance(val, dict) and val.get('showMorePaginationURL'):
            api_url = 'https:' + val['showMorePaginationURL']
            split_url = urlsplit(api_url)
            params = parse_qs(split_url.query)
            api_url = '{}://{}{}?limit=10&topic={}'.format(split_url.scheme, split_url.netloc, split_url.path, params['topic'][0])
            api_json = utils.get_url_json(api_url)
            if api_json:
                break
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['data']['articles']:
        if save_debug:
            logger.debug('getting content for ' + article['articleUrl'])
        item = get_content(article['articleUrl'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = preloaded_state['template']['metadataTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed