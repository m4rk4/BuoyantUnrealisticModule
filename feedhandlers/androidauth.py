import re, tldextract
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_json(url):
    tld = tldextract.extract(url)
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '/index.json'

    sites_json = utils.read_json_file('./sites.json')
    build_id = sites_json[tld.domain]['buildId']
    next_url = '{}://{}/_next/data/{}/en{}'.format(split_url.scheme, split_url.netloc, build_id, path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating androidauthority.com buildId')
        article_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', article_html)
        if m:
            sites_json[tld.domain]['buildId'] = m.group(1)
            utils.write_file(sites_json, './sites.json')
            next_url = '{}://{}/_next/data/{}/en{}'.format(split_url.scheme, split_url.netloc, m.group(1), path)
            next_json = utils.get_url_json(next_url)
            if not next_json:
                return None
    return next_json


def add_image(image):
    if image.get('srcSet'):
        img_src = utils.image_from_srcset(image['srcSet'], 1000)
    else:
        img_src = image['src']
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credits'):
        for it in image['credits']:
            captions.append(it['title'])
    if image.get('pLink'):
        link = utils.get_redirect_url(image['pLink']['href'])
    else:
        link = ''
    return utils.add_image(img_src, ' | '.join(captions), link=link)


def format_block(block):
    print(block)
    content_html = ''
    if block['resource'] == 'nc-string':
        content_html += block['html']

    elif re.search(r'^nc-.*\bimg$', block['resource']):
        content_html += add_image(block['image'])

    elif block['resource'] == 'nc-gallery':
        for image in block['items']:
            content_html += add_image(image) + '<br/>'

    elif block['resource'] == 'nc-img-comparison':
        if block['a']['image'].get('srcSet'):
            img_a = utils.image_from_srcset(block['a']['image']['srcSet'], 1000)
        else:
            img_a = block['a']['image']['src']
        if block['b']['image'].get('srcSet'):
            img_b = utils.image_from_srcset(block['b']['image']['srcSet'], 1000)
        else:
            img_b = block['b']['image']['src']
        content_html += '<table style="width:100%;"><tr><td style="width:50%"><img src="{}"/><br/><small>{}</small></td><td style="width:50%"><img src="{}"/><br/><small>{}</small></td></tr></table>'.format(
            img_a, block['a']['title'], img_b, block['b']['title'])

    elif block['resource'] == 'nc-embed':
        if block.get('video'):
            if block['video'].get('youtubeId'):
                content_html += utils.add_embed(
                    'https://www.youtube.com/watch?v={}'.format(block['video']['youtubeId']))
            else:
                logger.warning('unhandled nc-embed video')
        else:
            logger.warning('unhandled nc-embed')

    elif block['resource'] == 'nc-quote':
        content_html += utils.add_pullquote(block['html'], block.get('author'))

    elif block['resource'] == 'nc-alert':
        content_html += utils.add_blockquote(block['html'])

    elif block['resource'] == 'nc-tldr':
        content_html += utils.add_blockquote('<strong>TL;DR</strong><br/>' + block['html'])

    elif block['resource'] == 'nc-faq':
        content_html += '<h4 style="margin-bottom:0;">{}</h4>'.format(block['question'])
        for blk in block['blocks']:
            content_html += format_block(blk)

    elif block['resource'] == 'nc-table':
        content_html += '<table>'
        if block.get('headings'):
            content_html += '<tr>'
            for it in block['headings']:
                content_html += '<th>{}</th>'.format(it['html'])
            content_html += '</tr>'
        for row in block['cells']:
            content_html += '<tr>'
            for it in row:
                content_html += '<td>{}</td>'.format(it['html'])
            content_html += '</tr>'
        content_html += '</table>'

    elif block['resource'] == 'nc-columns':
        # Not actually putting these in columns
        column_html = ''
        for it in block['columns']:
            for blk in it['items']:
                column_html += format_block(blk)
        # These are generally lists, so combine them
        content_html += column_html.replace('</ul><ul>', '')

    elif block['resource'] == 'nc-poll':
        for poll in block['items']:
            content_html += '<blockquote><h3 style="margin:0;">Poll: {}</h3>'.format(poll['question'])
            for item in poll['items']:
                content_html += utils.add_bar(item['answer'], item['value'], poll['votes'], True)
            content_html += '</blockquote>'

    elif block['resource'] == 'nc-linked-buttons':
        for it in block['buttons']:
            content_html += '<p style="text-align:{};"><a href="{}"><strong>{}</strong></a></p>'.format(it['align'],
                                                                                                        utils.get_redirect_url(
                                                                                                            it['pLink'][
                                                                                                                'href']),
                                                                                                        it['label'])

    elif block['resource'] == 'nc-deals-simple':
        content_html += '<p style="text-align:center;"><strong>{}</strong> — <a href="{}">{}</a></p>'.format(
            block['title'], utils.get_redirect_url(block['link']['pLink']['href']), block['link']['label'])

    elif block['resource'] == 'nc-deals-detailed':
        content_html += '<div style="margin-left:20px;"><strong>{}</strong>'.format(block['title'])
        if block.get('tags'):
            content_html += '<br/>{}'.format('•'.join(block['tags']))
        if block.get('refLink'):
            content_html += '<br/>&#10148;&nbsp;<a href="{}">{}</a>'.format(block['refLink']['pLink']['href'],
                                                                            block['refLink']['label'])
        if block.get('link'):
            content_html += '<br/>&#10148;&nbsp;<a href="{}">{}</a>'.format(
                utils.get_redirect_url(block['link']['pLink']['href']), block['link']['label'])
        content_html += '</div>'

    elif block['resource'] == 'nc-deals-large':
        if block['image'].get('srcSet'):
            img_src = utils.image_from_srcset(block['image']['srcSet'], 300)
        else:
            img_src = block['image']['src']
        img_src = '{}/image?url={}&height=128'.format(config.server, quote_plus(img_src))
        content_html += '<table><tr><td><img src="{}"/></td><td style="vertical-align:top;"><h4 style="margin:0;">{}</h4><small>{}</small></td></tr></table><ul>'.format(
            img_src, block['title'], block['text'])
        for item in block['buttons']:
            content_html += '<li><a href="{}">{}</a></li>'.format(utils.get_redirect_url(item['link']['pLink']['href']),
                                                                  item['link']['label'])
        content_html += '</ul>'

    elif block['resource'] == 'nc-multi':
        for blk in block['blocks']:
            content_html += format_block(blk)

    elif re.search(r'nc-(ad|feedback|recommend|revcontent|section)', block['resource']):
        pass

    else:
        logger.warning('unhandled block ' + block['resource'])

    return content_html


def get_content(url, args, save_debug=False):
    next_json = get_next_json(url)
    if not next_json:
        return None

    page_json = next_json['pageProps']['page']
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    item['id'] = page_json['meta']['postId']
    item['url'] = page_json['pagePath']
    item['title'] = page_json['title']

    meta = next((it for it in page_json['head']['metaTags'] if it.get('property') == 'article:published_time'), None)
    if meta:
        dt = datetime.fromisoformat(meta['content'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    meta = next((it for it in page_json['head']['metaTags'] if it.get('property') == 'article:modified_time'), None)
    if meta:
        dt = datetime.fromisoformat(meta['content'])
        item['date_modified'] = dt.isoformat()

    if page_json.get('authors'):
        authors = []
        for it in page_json['authors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif page_json.get('meta') and page_json['meta'].get('dataLayer') and page_json['meta']['dataLayer'].get('author'):
        item['author'] = {"name": page_json['meta']['dataLayer']['author']}
    else:
        item['author'] = {"name": "Android Authority"}

    if page_json['meta'].get('subscribeTags'):
        item['tags'] = list(set(page_json['meta']['subscribeTags']))
    elif page_json['meta'].get('tags'):
        item['tags'] = list(set(page_json['meta']['tage']))

    meta = next((it for it in page_json['head']['metaTags'] if it.get('property') == 'og:image'), None)
    if meta:
        item['_image'] = meta['content']

    meta = next((it for it in page_json['head']['metaTags'] if it.get('name') == 'description'), None)
    if meta:
        item['summary'] = meta['content']

    item['content_html'] = ''
    if page_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(page_json['subtitle'])
    elif page_json.get('remarkHtml'):
        item['content_html'] += '<p><em>{}</em></p>'.format(page_json['remarkHtml'])

    if page_json.get('image'):
        item['content_html'] += add_image(page_json['image'])
    elif item.get('_image'):
        if page_json.get('blocks') and not (page_json['blocks'][0].get('image') or page_json['blocks'][0].get('video')):
            item['content_html'] += utils.add_image(item['_image'])

    if page_json.get('review'):
        badge = ''
        if page_json.get('badges'):
            for it in page_json['badges']:
                if re.search(r'recommended', it['src']):
                    badge = 'Recommended'
                elif re.search(r'editors_choice', it['src']):
                    badge = 'Editor\'s Choice'
        item[
            'content_html'] += '<div style="text-align:center"><strong>{}</strong><h1 style="margin:0;">{}</h1>{}</div><p><em>{}</em></p>'.format(
            page_json['review']['device']['name'], page_json['review']['device']['score'], badge,
            page_json['review']['bottomLine'])
        if page_json['review'].get('scores'):
            item['content_html'] += '<h3 style="margin-bottom:0;">Our scores</h3>'
            for it in page_json['review']['scores']:
                item['content_html'] += utils.add_bar(it['name'], it['value'], 10, False)

    if page_json.get('table'):
        item['content_html'] += '<h3 style="margin-bottom:0;">{}</h3>'.format(page_json['table']['positive']['title'])
        for it in page_json['table']['positive']['list']:
            item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:green;">&#10003;</span>&nbsp;{}</div>'.format(
                it)
        item['content_html'] += '<h3 style="margin-bottom:0;">{}</h3>'.format(page_json['table']['negative']['title'])
        for it in page_json['table']['negative']['list']:
            item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:red;">&#10007;</span>&nbsp;{}</div>'.format(it)

    if page_json.get('offers'):
        item['content_html'] += '<h3 style="margin-bottom:0;">{}</h3><ul style="margin-top:4px;">'.format(
            page_json['title'])
        for it in page_json['offers']['items']:
            item['content_html'] += '<li><a href="{}">{}</a>'.format(utils.get_redirect_url(it['url']),
                                                                     it['buttonLabel'])
        item['content_html'] += '</ul>'

    if page_json.get('stories'):
        for story in page_json['stories']:
            item['content_html'] += '<h2>{}</h2>'.format(story['title'])
            for block in story['blocks']:
                item['content_html'] += format_block(block)

    if page_json.get('roundup'):
        for story in page_json['roundup']:
            item['content_html'] += '<h2>{}</h2>'.format(story['title'])
            for block in story['blocks']:
                item['content_html'] += format_block(block)

    if page_json.get('fun'):
        for story in page_json['fun']:
            item['content_html'] += '<h2>{}</h2>'.format(story['title'])
            for block in story['blocks']:
                item['content_html'] += format_block(block)

    if page_json.get('blocks'):
        for block in page_json['blocks']:
            item['content_html'] += format_block(block)
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
