import re
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_json(url, site_json):
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '.json'

    next_url = '{}://{}/_next/data/{}/en{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating {} buildId'.format(split_url.netloc))
        article_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', article_html)
        if m and site_json['buildId'] != m.group(1):
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
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
    #print(block)
    content_html = ''
    if block['resource'] == 'nc-string':
        content_html += block['html']

    elif re.search(r'^nc-.*\bimg$', block['resource']):
        content_html += add_image(block['image'])

    elif block['resource'] == 'nc-gallery':
        for image in block['items']:
            content_html += add_image(image) + '<br/>'

    elif block['resource'] == 'nc-img-comparison':
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        if block['a']['image'].get('srcSet'):
            img_src = utils.image_from_srcset(block['a']['image']['srcSet'], 1000)
        else:
            img_src = block['a']['image']['src']
        captions = []
        if block['a']['image'].get('title'):
            captions.append(block['a']['image']['title'])
        if block['a']['image'].get('caption'):
            captions.append(block['a']['image']['caption'])
        if block['a']['image'].get('credits'):
            for it in block['a']['image']['credits']:
                captions.append(it['title'])
        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(img_src, ' | '.join(captions)))
        if block['b']['image'].get('srcSet'):
            img_src = utils.image_from_srcset(block['b']['image']['srcSet'], 1000)
        else:
            img_src = block['b']['image']['src']
        captions = []
        if block['b']['image'].get('title'):
            captions.append(block['b']['image']['title'])
        if block['b']['image'].get('caption'):
            captions.append(block['b']['image']['caption'])
        if block['b']['image'].get('credits'):
            for it in block['b']['image']['credits']:
                captions.append(it['title'])
        content_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(img_src, ' | '.join(captions)))
        content_html += '</div><div>&nbsp;</div/'

    elif block['resource'] == 'nc-embed':
        if block.get('video'):
            if block['video'].get('youtubeId'):
                content_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(block['video']['youtubeId']))
            else:
                logger.warning('unhandled nc-embed video')
        else:
            logger.warning('unhandled nc-embed')

    elif block['resource'] == 'nc-embed-youtube':
        content_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(block['video']['youtubeId']))

    elif block['resource'] == 'nc-twitter':
        content_html += utils.add_embed('https://twitter.com/__/status/{}'.format(block['id']))

    elif block['resource'] == 'nc-audio':
        content_html += '<div style="display:flex; align-items:center; margin-left:2em;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Play</a></span></div>'.format(block['link'], config.server)

    elif block['resource'] == 'nc-quote':
        content_html += utils.add_pullquote(block['html'], block.get('author'))

    elif block['resource'] == 'nc-alert':
        content_html += '<div style="padding:1em; background-color:lightgrey; border-radius:10px;"><p>{}</p></div>'.format(block['html'])

    elif block['resource'] == 'nc-opinion':
        content_html += '<div style="padding:1em; background-color:lightgrey; border-radius:10px;"><p>{}</p></div>'.format(block['hint'])

    elif block['resource'] == 'nc-disclosure-box':
        content_html += '<div style="padding:1em; background-color:lightgrey; border-radius:10px;">'
        for blk in block['blocks']:
            content_html += format_block(blk)
        content_html += '</div>'

    elif block['resource'] == 'nc-tldr':
        content_html += utils.add_blockquote('<strong>TL;DR</strong><br/>' + block['html'])

    elif block['resource'] == 'nc-faq':
        content_html += '<h3 style="margin-bottom:0;">{}</h3>'.format(block['question'])
        for blk in block['blocks']:
            content_html += format_block(blk)

    elif block['resource'] == 'nc-table':
        content_html += '<table style="width:100%; border-collapse:collapse;">'
        if block.get('headings'):
            content_html += '<tr style="border-collapse:collapse;">'
            for it in block['headings']:
                content_html += '<td style="padding:0.3em; border-bottom:1px solid black; border-collapse:collapse; background-color:black;"><span style="color:white; font-weight:bold;">{}</span></td>'.format(it['html'])
            content_html += '</tr>'
        for i, row in enumerate(block['cells']):
            if i%2:
                color = 'lightgrey'
            else:
                color = 'white'
            content_html += '<tr style="border-collapse:collapse;">'
            for it in row:
                content_html += '<td style="padding:0.3em; border-bottom:1px solid black; border-collapse:collapse; background-color:{};">{}</td>'.format(color, it['html'])
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
            content_html += '<h3>Poll: {}</h3>'.format(poll['question'])
            for item in poll['items']:
                content_html += utils.add_bar(item['answer'], item['value'], poll['votes'], True)
            content_html += '<div>&nbsp;</div>'

    elif block['resource'] == 'nc-linked-buttons':
        for it in block['buttons']:
            content_html += '<p style="text-align:{};"><a href="{}"><strong>{}</strong></a></p>'.format(it['align'], utils.get_redirect_url(it['pLink']['href']), it['label'])

    elif block['resource'] == 'nc-deals-simple':
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; border:1px solid black; border-radius:10px;"><div style="flex:1; min-width:256px; margin:1em;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(block['title'])
        if block.get('refLink'):
            content_html += '<br/><small><a href="{}">{}</a></small>'.format(block['refLink']['pLink']['href'], block['refLink']['label'])
        content_html += '</div><div style="flex:1; min-width:256px; margin:1em; text-align:center;"><span style="padding:0.4em; font-weight:bold; background-color:#00d49f;"><a href="{}" style="color:white;">{}</a></span></div></div>'.format(utils.get_redirect_url(block['buttons'][0]['link']['pLink']['href']), block['buttons'][0]['link']['label'])

    elif block['resource'] == 'nc-deals-detailed':
        content_html += '<div style="margin-left:20px;"><strong>{}</strong>'.format(block['title'])
        if block.get('tags'):
            content_html += '<br/>{}'.format('•'.join(block['tags']))
        if block.get('refLink'):
            content_html += '<br/>&#10148;&nbsp;<a href="{}">{}</a>'.format(block['refLink']['pLink']['href'], block['refLink']['label'])
        if block.get('link'):
            content_html += '<br/>&#10148;&nbsp;<a href="{}">{}</a>'.format(
                utils.get_redirect_url(block['link']['pLink']['href']), block['link']['label'])
        content_html += '</div>'

    elif block['resource'] == 'nc-deals-medium':
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in block['items']:
            content_html += '<div style="flex:1; min-width:128px; max-width:256px; margin:auto; padding:8px; border:1px solid black; border-radius:10px;">'
            if it['image'].get('srcSet'):
                img_src = utils.image_from_srcset(it['image']['srcSet'], 300)
            else:
                img_src = it['image']['src']
            content_html += '<img src="{}" style="width:100%;" />'.format(img_src)
            content_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">{}</div>'.format(it['title'])
            if it.get('buttons'):
                content_html += '<div style="text-align:center"><a href="{}">{}</a></div>'.format(it['buttons'][0]['link']['pLink']['href'], it['buttons'][0]['link']['label'])
            if it.get('tags'):
                content_html += '<div style="text-align:center">{}</div>'.format('<br/>'.join(it['tags']))
            content_html += '</div>'
        content_html += '</div>'

    elif block['resource'] == 'nc-deals-large':
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; border:1px solid black; border-radius:10px;">'
        if block['image'].get('srcSet'):
            img_src = utils.image_from_srcset(block['image']['srcSet'], 300)
        else:
            img_src = block['image']['src']
        # img_src = '{}/image?url={}&height=128'.format(config.server, quote_plus(img_src))
        #content_html += '<table><tr><td><img src="{}"/></td><td style="vertical-align:top;"><h4 style="margin:0;">{}</h4><small>{}</small></td></tr></table><ul>'.format(img_src, block['title'], block['text'])
        content_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(img_src)
        content_html += '<div style="flex:2; min-width:256px; margin:1em;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(block['title'])
        if block.get('subtitle'):
            content_html += '<br/><b>{}</b>'.format(block['subtitle'])
        if block.get('tags'):
            content_html += '<br/><small>{}</small>'.format('&bull;'.join(block['tags']))
        if block.get('score'):
            content_html += '<br/>Rating: {}'.format(block['score'])
        content_html += '<ul>'
        for item in block['buttons']:
            content_html += '<li><a href="{}">{}</a></li>'.format(utils.get_redirect_url(item['link']['pLink']['href']), item['link']['label'])
        content_html += '</ul></div></div>'

    elif block['resource'] == 'nc-best-product-title':
        content_html += '<div style="display:flex; justify-content:space-between; margin-top:1em;"><p><span style="font-size:1.2em; font-weight:bold;">{}</span></p><p><span style="font-size:1.2em; font-weight:bold;">Rating: {}</span></p></div>'.format(block['title'], block['score'])

    elif block['resource'] == 'nc-best-product-gallery':
        content_html += '<div style="border:1px solid black; border-radius:10px;">'
        content_html += '<div style="font-size:0.9em; margin:1em;">'
        if block['headLabel']['icon'] == 'best':
            content_html += '&#129351;'
        elif block['headLabel']['icon'] == 'features':
            content_html += '&#9776;'
        elif block['headLabel']['icon'] == 'money':
            content_html += '&#128176;'
        elif block['headLabel']['icon'] == 'on_ears':
            content_html += '&#127911;'
        content_html += '&nbsp;{}</div>'.format(block['headLabel']['title'])
        if block['images'][0].get('srcSet'):
            img_src = utils.image_from_srcset(block['images'][0]['srcSet'], 300)
        else:
            img_src = block['images'][0]['src']
        content_html += utils.add_image(img_src)
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;"><div style="flex:1; min-width:256px; margin:1em;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(block['title'])
        if block.get('reviewLink'):
            content_html += '<br/><small><a href="{}">{}</a></small>'.format(block['reviewLink']['pLink']['href'], block['reviewLink']['label'])
        content_html += '</div>'
        content_html += '<div style="flex:1; min-width:256px; margin:1em; text-align:center;"><span style="padding:0.4em; font-weight:bold; background-color:#00d49f;"><a href="{}" style="color:white;">Buy now</a></span></div>'.format(utils.get_redirect_url(block['productLink']['href']))
        content_html += '</div></div>'

    elif block['resource'] == 'nc-multi':
        for blk in block['blocks']:
            content_html += format_block(blk)

    elif re.search(r'nc-(ad|affilate|feedback|faq-submission|recommend|revcontent|section)', block['resource']):
        pass

    else:
        logger.warning('unhandled block ' + block['resource'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, site_json)
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
        if page_json['authors'].get('authoredBy'):
            for it in page_json['authors']['authoredBy']:
                authors.append(it['name'])
        if page_json['authors'].get('reviewedBy'):
            for it in page_json['authors']['reviewedBy']:
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
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        if page_json.get('badges'):
            item['content_html'] += '<div style="flex:1; max-width:256px; min-width:128px; margin:auto;">'
            for it in page_json['badges']:
                item['content_html'] += '<img src="{}" style="width:100%;" />'.format(it['src'])
            item['content_html'] += '</div>'
        item['content_html'] += '<div style="flex:2; min-width:256px;">'
        item['content_html'] += '<h2>{}</h2>'.format(page_json['review']['device']['name'])
        item['content_html'] += '<div style="display:flex; align-items:center;"><span style="font-size:1.2em; font-weight:bold;">Rating:</span>&nbsp;<span style="font-size:2em; font-weight:bold;">{}</span></div>'.format(page_json['review']['device']['score'])
        item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">The Bottom Line</div><div style="margin-left:0.5em; font-style:italic;">{}</div>'.format(page_json['review']['bottomLine'])
        item['content_html'] += '</div></div>'
        if page_json['review'].get('scores'):
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">Scores</div><div style="margin-left:0.5em;">'
            for it in page_json['review']['scores']:
                item['content_html'] += utils.add_bar(it['name'], it['value'], 10, False)
            item['content_html'] += '</div>'

    if page_json.get('device'):
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        if page_json.get('badges'):
            item['content_html'] += '<div style="flex:1; max-width:256px; min-width:128px; margin:auto;">'
            for it in page_json['badges']:
                item['content_html'] += '<img src="{}" style="width:100%;" />'.format(it['src'])
            item['content_html'] += '</div>'
        item['content_html'] += '<div style="flex:2; min-width:256px;">'
        item['content_html'] += '<h2>{}</h2>'.format(page_json['device']['name'])
        item['content_html'] += '<div style="display:flex; align-items:center;"><span style="font-size:1.2em; font-weight:bold;">Rating:</span>&nbsp;<span style="font-size:2em; font-weight:bold;">{}</span></div>'.format(page_json['device']['ourScore'])
        if page_json.get('bottomLineContent'):
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">The Bottom Line</div><div style="margin-left:0.5em; font-style:italic;">{}</div>'.format(page_json['bottomLineContent']['text'])
        item['content_html'] += '</div></div>'
        if page_json.get('features'):
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">Features</div><table style="margin-left:0.5em; width:100%; border-collapse:collapse;">'
            for i, it in enumerate(page_json['features']):
                if i % 2:
                    color = 'white'
                else:
                    color = 'lightgrey'
                item['content_html'] += '<tr style="border-collapse:collapse;"><td style="border-collapse:collapse; border-top:1px solid black; border-bottom:1px solid black; background-color:{}; padding:0.3em;">{}</td><td style="border-collapse:collapse; border-top:1px solid black; border-bottom:1px solid black; background-color:{}; padding:0.3em;">{}</td></tr>'.format(color, it['desc'], color, ', '.join(it['val']))
            item['content_html'] += '</table>'
        if page_json.get('scores'):
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">Scores</div><div style="margin-left:0.5em;">'
            for it in page_json['scores']:
                item['content_html'] += utils.add_bar(it['label'], it['ourScore'], 10, False)
            item['content_html'] += '</div>'

    if page_json.get('table'):
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        item['content_html'] += '<div style="flex:1; min-width:256px;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(page_json['table']['positive']['title'])
        for it in page_json['table']['positive']['list']:
            item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:green;">&#10003;</span>&nbsp;{}</div>'.format(it)
        item['content_html'] += '</div><div style="flex:1; min-width:256px;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(page_json['table']['negative']['title'])
        for it in page_json['table']['negative']['list']:
            item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:red;">&#10007;</span>&nbsp;{}</div>'.format(it)
        item['content_html'] += '</div></div><div>&nbsp;</div>'

    if page_json.get('offers'):
        item['content_html'] += '<h3 style="margin-bottom:0;">{}</h3><ul style="margin-top:4px;">'.format(
            page_json['title'])
        for it in page_json['offers']['items']:
            item['content_html'] += '<li><a href="{}">{}</a>'.format(utils.get_redirect_url(it['url']), it['buttonLabel'])
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

    if page_json.get('bestList'):
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in page_json['bestList']:
            item['content_html'] += '<div style="flex:1; min-width:240px; max-width:360px; padding:1em; border:1px solid black; border-radius:10px;">'
            item['content_html'] += '<div style="font-size:0.8em; font-weight:bold; text-align:center;">'
            if it['headLabel']['icon'] == 'best':
                item['content_html'] += '&#129351;'
            elif it['headLabel']['icon'] == 'features':
                item['content_html'] += '&#9776;'
            elif it['headLabel']['icon'] == 'money':
                item['content_html'] += '&#128176;'
            elif it['headLabel']['icon'] == 'on_ears':
                item['content_html'] += '&#127911;'
            item['content_html'] += '&nbsp;{}</div>'.format(it['headLabel']['title'])
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(it['title'])
            item['content_html'] += '<div style="font-size:0.8em;">By {}</div>'.format(it['manufacturer'])
            if it['image'].get('srcSet'):
                img_src = utils.image_from_srcset(it['image']['srcSet'], 1000)
            else:
                img_src = it['image']['src']
            item['content_html'] += '<img src="{}" style="width:100%;" />'.format(img_src)
            item['content_html'] += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">Rating: {}</div>'.format(it['score'])
            if it.get('positives'):
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">Positives</div>'
                for li in it['positives']:
                    item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:green;">&#10003;</span>&nbsp;{}</div>'.format(li)
            if it.get('negatives'):
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">Negatives</div>'
                for li in it['negatives']:
                    item['content_html'] += '<div>&nbsp;&nbsp;<span style="color:red;">&#10007;</span>&nbsp;{}</div>'.format(li)
            if it.get('bottomLine'):
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">The Bottom Line</div><div>{}</div>'.format(it['bottomLine'])
            if it.get('reviewButton'):
                item['content_html'] += '<div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(it['reviewButton']['pLink']['href'], it['reviewButton']['label'])
            if it.get('shopLink'):
                item['content_html'] += '<div style="font-weight:bold;"><a href="{}">&#128722;&nbsp;Check price</a></div>'.format(it['shopLink']['href'])
            item['content_html'] += '</div>'
        item['content_html'] += '</div>'

    if page_json.get('blocks'):
        for block in page_json['blocks']:
            item['content_html'] += format_block(block)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
