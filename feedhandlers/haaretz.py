import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url, user_agent='facebook')
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(el.string)


def render_content(node, apollo_state):
    content_html = ''
    content_node = apollo_state[node['id']]
    if content_node['__typename'] == 'HtmlNode':
        content = re.sub(r'href="(/[^"]+)"', r'href="https://www.haaretz.com\1"', content_node['content'])
        content_html += '<{0}>{1}</{0}>'.format(content_node['tag'], content)
    elif content_node['__typename'] == 'Enhancement':
        for it in content_node['item']:
            content_html += render_content(it, apollo_state)
    elif content_node['__typename'] == 'EmbedRichTextElement':
        content_html += render_content(content_node['content'], apollo_state)
    elif content_node['__typename'] == 'QuoteRichTextElement':
        content_html += utils.add_pullquote(content_node['quote'], content_node.get('subText'))
    elif content_node['__typename'] == 'ImageRichTextElement':
        content_html += render_content(content_node['image'], apollo_state)
    elif content_node['__typename'] == 'Gallery':
        for it in content_node['images']:
            content_html += render_content(it, apollo_state)
    elif content_node['__typename'] == 'htz_image_Image':
        if content_node['name'] != 'HDC app download banner':
            file = apollo_state[content_node['files'][0]['id']]
            img_src = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/' + file['path']
            captions = []
            if content_node.get('caption'):
                captions.append(content_node['caption'])
            if content_node.get('credit'):
                captions.append(content_node['credit'])
            content_html += utils.add_image(img_src, ' | '.join(captions), link=content_node.get('link'))
    elif content_node['__typename'] == 'Youtube' or content_node['__typename'] == 'GoogleMaps':
        content_html += utils.add_embed(content_node['source'])
    elif content_node['__typename'] == 'Twitter':
        m = re.findall(r'href="([^"]+)"', content_node['content'])
        content_html += utils.add_embed(m[-1])
    elif content_node['__typename'] == 'Instagram':
        m = re.search(r'data-instgrm-permalink="([^"]+)"', content_node['source'])
        content_html += utils.add_embed(m.group(1))
    elif content_node['__typename'] == 'PodcastEpisode':
        image = apollo_state[content_node['image']['id']]
        file = apollo_state[image['files'][0]['id']]
        img_src = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/' + file['path']
        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(img_src))
        content_html += '<table><tr><td><a href="{0}"><img src="{1}" /></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold; margin-bottom:4px;"><a href="{0}">{2}</a></div>'.format(content_node['url'], poster, content_node['title'])
        channel = apollo_state[content_node['channel']['id']]
        links = apollo_state[channel['links']['id']]
        content_html += '<div>by <a href="{}">{}</a></div></td></tr></table>'.format(links['spotify'], channel['channelName'])
    elif content_node['__typename'] == 'OmnyStudio':
        if 'Haaretz Weekly' in content_node['title']:
            img_src = 'https://img.haarets.co.il/bs/0000017f-da28-d249-ab7f-fbe8df740000/0e/8b/dd52f29a5b29b9e4d32747cff5b9/3315319277.png?height=128&width=128'
            poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(img_src))
            content_html += '<table><tr><td><a href="{}"><img src="{}" /></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold; margin-bottom:4px;"><a href="{}">{}</a></div><div>by <a href="https://omny.fm/shows/haaretz-weekly">Haaretz Weekly</a></td></tr></table>'.format(content_node['fileUrl'], poster, content_node['source'], content_node['title'])
        else:
            logger.warning('unhandled OmnyStudio node')
    elif content_node['__typename'] == 'DfpBannerRichTextElement' or content_node['__typename'] == 'RegistrationRichTextElement' or content_node['__typename'] == 'RelatedArticles':
        pass
    else:
        logger.warning('unhandled node type {} {}'.format(content_node['__typename'], node['id']))
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    apollo_state = next_data['props']['apolloState']
    root_query = apollo_state['ROOT_QUERY']
    page = root_query['Page({{\"id\":\"{}\"}})'.format(root_query['articleId'])]
    page = apollo_state[page['id']]
    article = apollo_state['{}:{}'.format(page['pageType'], page['contentId'])]
    # if root_query['articleType'] == 'standardArticle':
    #     if 'ty-article-opinion' in url:
    #         article = apollo_state['StandardArticle:{}'.format(root_query['articleId'])]
    #     else:
    #         article = apollo_state['StandardArticle:{}'.format(root_query['articleId'])]
    # elif root_query['articleType'] == 'liveBlogArticle':
    #     article = apollo_state['LiveBlogArticle:{}'.format(root_query['articleId'])]
    # elif root_query['articleType'] == 'magazineArticle':
    #     article = apollo_state['MagazineArticle:{}'.format(root_query['articleId'])]
    # else:
    #     logger.warning('unhandled articleType {} in {}'.format(root_query['articleType'], url))
    #     return None
    return get_item(article, apollo_state, args, site_json, save_debug)


def get_item(article, apollo_state, args, site_json, save_debug):
    item = {}
    if article['__typename'] == 'LiveBlogItem':
        item['id'] = article['itemId']
        item['url'] = article['itemUrl']
        dt = datetime.fromtimestamp(article['publishDate']/1000).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromtimestamp(article['updateDate']/1000).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()
    else:
        item['id'] = article['contentId']
        item['url'] = article['canonicalLink']
        dt = datetime.fromisoformat(article['datePublished']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(article['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['title'] = article['title']

    item['author'] = {}
    authors = []
    avatar = ''
    for it in article['authors']:
        author = apollo_state[it['id']]
        authors.append(author['name'])
        if author.get('image'):
            image = apollo_state[author['image']['id']]
            file = apollo_state[image['files'][0]['id']]
            img_src = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/{}?height=120&width=120'.format(file['path'])
            if file.get('crops'):
                crop = apollo_state[file['crops']['id']]
                if crop.get('square'):
                    crop = apollo_state[crop['square']['id']]
                    img_src += '&precrop={},{},x{},y{}'.format(crop['width'], crop['height'], crop['x'], crop['y'])
            avatar += '<img src="{}/image?url={}&width=60&height=60&mask=ellipse" />'.format(config.server, quote_plus(img_src))
        else:
            avatar += '<img src="{}/image?width=60&height=60&mask=ellipse" />'.format(config.server)
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'Haaretz'
        img_src = 'https://img.haarets.co.il/bs/0000017f-da24-d42c-afff-dff6b5730000/3f/38/eeda180aadf7ba784170c5640a2e/1571195916.png?height=120&width=120'
        avatar += '<img src="{}/image?url={}&width=60&height=60&mask=ellipse" />'.format(config.server, quote_plus(img_src))

    if article.get('tags'):
        item['tags'] = []
        for it in article['tags']:
            tag = apollo_state[it['id']]
            item['tags'].append(tag['name'])

    item['content_html'] = ''
    if article['__typename'] == 'LiveBlogItem':
        item['content_html'] += '<table><tr><td>{}</td><td>{}<br/>{}</td></tr></table>'.format(avatar, item['author']['name'], item['_display_date'])
        item['content_html'] += '<h3><a href="{}">{}</a></h3>'.format(item['url'], item['title'])

    if article.get('subTitle'):
        item['summary'] = article['subTitle']
        item['content_html'] += '<p><em>{}</em></p>'.format(article['subTitle'])

    gallery = ''
    if article.get('openingElement'):
        if article['openingElement']['typename'] == 'htz_image_Image':
            image = apollo_state[article['openingElement']['id']]
            file = apollo_state[image['files'][0]['id']]
            item['_image'] = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/' + file['path']
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('credit'):
                captions.append(image['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
        elif article['openingElement']['typename'] == 'Gallery':
            element = apollo_state[article['openingElement']['id']]
            image = apollo_state[element['images'][0]['id']]
            file = apollo_state[image['files'][0]['id']]
            item['_image'] = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/' + file['path']
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('credit'):
                captions.append(image['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
            gallery = render_content(article['openingElement'], apollo_state)
        elif article['openingElement']['typename'] == 'PodcastEpisode':
            element = apollo_state[article['openingElement']['id']]
            image = apollo_state[element['image']['id']]
            file = apollo_state[image['files'][0]['id']]
            item['_image'] = 'https://img.haarets.co.il/bs/0000018b-138a-d2fc-a59f-d39b1f800000/' + file['path']
            item['content_html'] += render_content(element['image'], apollo_state)
            item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen</a></span></div>'.format(element['url'], config.server)

    if article.get('tldr'):
        item['content_html'] += '<h2>TL:DR</h2>'
        for node in article['tldr']:
            item['content_html'] += render_content(node, apollo_state)
        item['content_html'] += '<div>&nbsp;</div><hr/>'

    if article.get('body'):
        for node in article['body']:
            item['content_html'] += render_content(node, apollo_state)

    if gallery:
        item['content_html'] += '<div>&nbsp;</div><hr/><h2>Gallery</h2>' + re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', gallery)

    if article.get('liveBlogItems'):
        item['content_html'] += '<div>&nbsp;</div><hr/><h2>Updates</h2>'
        for i, it in enumerate(article['liveBlogItems']):
            #print(it['id'])
            if i > 0:
                item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            blog_item = get_item(apollo_state[it['id']], apollo_state, args, site_json, save_debug)
            item['content_html'] += blog_item['content_html']
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
