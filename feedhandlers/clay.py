import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


# https://github.com/clay/clay
# https://docs.clayplatform.io/clay/

def get_content_html(content_uri):
    # Skip these
    if re.search(r'\/_components\/(future-tense-kicker|in-article-recirc|magazine-issue-|newsletter-|partner-branding|related|single-related-story|slate-kicker-promo|social-share)', content_uri):
        return ''

    # Handle these without loading the content_uri
    if '/divider/' in content_uri:
        return '<hr width="80%" />'

    content_json = utils.get_url_json('https://' + content_uri)
    if not content_json:
        return ''

    content_html = ''
    if re.search(r'\/\w+-paragraph\/', content_uri):
        if content_json.get('componentVariation') and content_json['componentVariation'] == 'clay-paragraph_drop-cap':
            if content_json['text'].startswith('<'):
                n = content_json['text'].find('>') + 1
            else:
                n = 0
            content_html = '<p>{}<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}</p>'.format(
                content_json['text'][0:n], content_json['text'][n], content_json['text'][n + 1:])
        else:
            content_html = '<p>{}</p>'.format(content_json['text'])

    elif re.search(r'\/(subhead|\w+-subheader)\/', content_uri):
        if content_json.get('headlineLevel'):
            content_html = '<{0}>{1}</{0}>'.format(content_json['headlineLevel'], content_json['text'])
        else:
            content_html = '<h3>{}</h3>'.format(content_json['text'])

    elif re.search(r'\/\w+-section-div\/', content_uri):
        if content_json.get('div'):
            logger.warning('unhandled section-div in https://' + content_uri)

    elif '/image/' in content_uri or '/image-sequence-item/' in content_uri:
        caption = []
        if content_json.get('imageCaption'):
            caption.append(content_json['imageCaption'].strip())
        elif content_json.get('caption'):
            caption.append(content_json['caption'].strip())
        if content_json.get('imageType'):
            caption.append(content_json['imageType'].strip() + ':')
        if content_json.get('imageCredit'):
            caption.append(content_json['imageCredit'].strip())
        elif content_json.get('credit'):
            caption.append(content_json['credit'].strip())
        content_html = utils.add_image(content_json['imageUrl'], ' | '.join(caption))

    elif '/image-sequence/' in content_uri:
        for image in content_json['images']:
            content_html += get_content_html(image['_ref'])

    elif '/image-collection/' in content_uri:
        for image in content_json['imageCollection']:
            caption = []
            if image.get('imageCaption'):
                caption.append(image['imageCaption'].strip())
            if image.get('imageType'):
                caption.append(image['imageType'].strip() + ':')
            if image.get('imageCredit'):
                caption.append(image['imageCredit'].strip())
            else:
                if content_json['imageCollection'][-1].get('imageCredit'):
                    caption.append(content_json['imageCollection'][-1]['imageCredit'].strip())
            content_html = utils.add_image(image['imageUrl'], ' '.join(caption))

    elif '/video/' in content_uri:
        if content_json.get('youtubeId'):
            content_html = utils.add_embed('https://www.youtube.com/watch?v=' + content_json['youtubeId'])
        else:
            logger.warning('unhandled video content in https://' + content_uri)

    elif re.search(r'\/\w+-external-video\/', content_uri):
        if content_json.get('url'):
            content_html = utils.add_embed(content_json['url'])
        else:
            logger.warning('unhandled external video content in https://' + content_uri)

    elif '/blockquote/' in content_uri or '/slate-blockquote/' in content_uri:
        soup = BeautifulSoup(content_json['text'], 'html.parser')
        if soup:
            for p in soup.find_all('p'):
                p.unwrap()
            text = str(soup)
            text = text.replace('<br/>', '<br/><br/>')
        else:
            text = content_json['text']
        if content_json.get('citation'):
            content_html = utils.add_pullquote(text, content_json['citation'])
        else:
            content_html = utils.add_blockquote(text)

    elif '/pull-quote/' in content_uri:
        text = content_json['quote']
        if content_json.get('attribution'):
            text += '<br />&mdash;&nbsp;{}'.format(content_json['attribution'])
        content_html = utils.add_pullquote(text)

    elif '/source-links/' in content_uri:
        for src in content_json['content']:
            text = []
            if src.get('title'):
                text.append(src['title'])
            if src.get('publication'):
                text.append(src['publication'])
            content_html = '<p>Source: <a href="{}">{}</a></p>'.format(src['url'], ' '.join(text))

    elif re.search(r'\/\w+-tweet\/', content_uri):
        if content_json.get('url'):
            content_html = utils.add_embed(content_json['url'])
        else:
            m = re.findall(r'https:\/\/twitter\.com\/[^\/]+/status/\d+', content_json['html'])
            if m:
                content_html = utils.add_embed(m[-1])
            else:
                logger.warning('unable to determine twitter url in https://' + content_uri)

    elif re.search(r'\/\w+-instagram\/', content_uri):
        if content_json.get('url'):
            content_html = utils.add_embed(content_json['url'])
        else:
            m = re.search(r'data-instgrm-permalink="([^\?"]+)', content_json['html'])
            if m:
                content_html = utils.add_embed(m.group(1))
            else:
                logger.warning('unable to determine instagram url in https://' + content_uri)

    elif re.search(r'\/\w+-megaphone\/', content_uri):
        content_html = utils.add_embed(content_json['publicIframeUrl'])

    elif '/subsection/' in content_uri:
        content_html = ''
        if content_json['borders']['top'] == True:
            content_html += '<hr width="80%">'
        if content_json.get('title'):
            content_html += '<h4>{}</h4>'.format(content_json['title'])
        for content in content_json['content']:
            content_html += get_content_html(content['_ref'])
        if content_json['borders']['bottom'] == True:
            content_html += '<hr width="80%">'

    elif '/errata/' in content_uri:
        content_html = content_json['text']

    elif '/product/' in content_uri:
        caption = []
        if content_json.get('imageCaption'):
            caption.append(content_json['imageCaption'].strip())
        if content_json.get('imageType'):
            caption.append(content_json['imageType'].strip() + ':')
        if content_json.get('imageCredit'):
            caption.append(content_json['imageCredit'].strip())
        content_html = utils.add_image(content_json['dynamicProductImage']['url'], ' '.join(caption))
        content_html += '<h4>{}</h4>'.format(content_json['agora']['name'])
        for desc in content_json['description']:
            content_html += get_content_html(desc['_ref'])
        content_html += '<ul>'
        for merch in content_json['agora']['merchants']:
            content_html += '<li><a href="{}">{}</a>: ${}</li>'.format(utils.get_redirect_url(merch['buyUrl']), merch['name'], merch['price'])
        content_html += '</ul>'

    elif '/package-list/' in content_uri:
        content_html = '<h3>{}</h3><ul>'.format(content_json['title'])
        for it in content_json['articles']:
            content_html += '<li><a href="{}">{}</a></li>'.format(it['canonicalUrl'], it['primaryHeadline'])
        content_html += '</ul>'

    else:
        logger.warning('unhandled content in https://' + content_uri)
    return content_html


def get_content(url, args, site_json, save_debug=False, page_uri=''):
    if not page_uri:
        article_html = utils.get_url_html(url)
        if article_html:
            soup = BeautifulSoup(article_html, 'html.parser')
            page_uri = soup.html['data-uri']

    if not page_uri:
        logger.warning('unable to determine data-uri for ' + url)
        return None

    article_uri = ''
    page_json = utils.get_url_json('https://' + page_uri)
    if page_json:
        for page in page_json['main']:
            if '/article/' in page:
                article_uri = page
                break
    if not article_uri:
        logger.warning('unable to determine article uri in ' + url)
        return None

    article_json = utils.get_url_json('https://' + article_uri)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_uri
    item['url'] = article_json['canonicalUrl']

    if article_json.get('overrideHeadline'):
        item['title'] = article_json['overrideHeadline']
    elif article_json.get('primaryHeadline'):
        item['title'] = article_json['primaryHeadline']
    elif article_json.get('pageTitle'):
        item['title'] = article_json['pageTitle']
    elif article_json.get('kilnTitle'):
        item['title'] = article_json['kilnTitle']
    if re.search(r'</', item['title']):
        item['title'] = BeautifulSoup(item['title'], 'html.parser').get_text()

    dt = datetime.fromisoformat(article_json['date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    for author in article_json['authors']:
        authors.append(author['text'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        tags_json = utils.get_url_json('https://' + article_json['tags']['_ref'])
        if tags_json:
            item['tags'] = []
            for it in tags_json['items']:
                item['tags'].append(it['text'])
    if not item.get('tags'):
        if article_json.get('tag'):
            item['tags'] = []
            for it in article_json['tag']:
                item['tags'].append(it['text'])
        elif article_json.get('normalizedTags'):
            item['tags'] = article_json['normalizedTags'].copy()

    if article_json.get('pageDescription'):
        item['summary'] = article_json['pageDescription']
    elif article_json.get('dek'):
        item['summary'] = article_json['dek']

    item['content_html'] = ''

    if article_json.get('ledeUrl'):
        item['_image'] = article_json['ledeUrl']
        caption = []
        if article_json.get('ledeCaption'):
            caption.append(article_json['ledeCaption'].strip())
        if article_json.get('ledeImageType'):
            caption.append(article_json['ledeImageType'].strip() + ':')
        if article_json.get('ledeCredit'):
            caption.append(article_json['ledeCredit'].strip())
        item['content_html'] += utils.add_image(article_json['ledeUrl'], ' '.join(caption))
    elif article_json.get('topImage'):
        for content in article_json['topImage']:
            item['content_html'] += get_content_html(content['_ref'])

    for content in article_json['content']:
        item['content_html'] += get_content_html(content['_ref'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
