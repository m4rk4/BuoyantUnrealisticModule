import html, json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.query:
        query = re.sub(r'w=\d+', 'w={}'.format(width), split_url.query)
        query = re.sub(r'(\?|&)h=\d+', '', query)
    else:
        query = 'w={}'.format(width)
    return '{}://{}{}?{}'.format(split_url.scheme, split_url.netloc, split_url.path, query)


def add_image(el, gallery=False, width=1000):
    if gallery:
        img = el.find(class_='img-gallery-thumbnail-img')
    else:
        img = el.find(attrs={"data-img-url": True})
    img_src = ''
    if img and img.get('data-img-url'):
        img_src = img['data-img-url']
    else:
        src = el.find('source')
        if src:
            img_src = src['srcset']
    if not img_src:
        logger.warning('image with unknown src')
        return ''
    if img and img.get('data-img-caption'):
        caption = re.sub('^"|"$', '', img['data-img-caption'])
        if caption == 'null':
            caption = ''
    else:
        caption = ''
    image_html = utils.add_image(resize_image(img_src, width), caption)
    if el.find_parent('li'):
        image_html = '<div>&nbsp;</div>' + image_html + '<div>&nbsp;</div>'
    return image_html


def add_play_store_app(el):
    new_html = '<table><tr>'
    it = el.find('img')
    if it:
        new_html += '<td style="vertical-align:top;"><img src="{}/image?url={}&width=128" style="width:128px;"/></td>'.format(config.server, quote_plus(it['src']))
    new_html += '<td style="vertical-align:top;">'
    it = el.find(class_='app-widget-name')
    if it:
        new_html += '<span style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></span>'.format(it['href'], it.get_text().strip())
    it = el.find(class_='app-developer-name')
    if it:
        if it.a:
            new_html += '<br/><a href="{}">{}</a>'.format(it.a['href'], it.get_text().strip())
        else:
            new_html += '<br/>{}'.format(it.get_text().strip())
    it = el.find(class_='app-widget-price')
    if it:
        new_html += '<br/><small>{}</small>'.format(it.get_text().strip())
    it = el.find(class_=re.compile(r'app-widget-rating'))
    if it:
        new_html += '<br/><small>Rating: {}</small>'.format(it.get_text().strip())
    it = el.find(class_='app-widget-download')
    if it:
        new_html += '<br/><a href="{}">{}</a>'.format(it['href'], it.get_text().strip())
    new_html += '</td></tr></table>'
    return new_html


def get_content(url, args, site_json, save_debug=False):
    # Sites: https://www.valnetinc.com/en/publishing-detail#our_brand
    split_url = urlsplit(url)
    article_json = utils.get_url_json('{}://{}/fetch/next-article{}'.format(split_url.scheme, split_url.netloc, split_url.path))
    if article_json:
        if save_debug:
            utils.write_file(article_json, './debug/debug.json')
        soup = BeautifulSoup(article_json['html'], 'html.parser')

    item = {}
    if article_json and article_json.get('gaCustomDimensions'):
        item['id'] = article_json['gaCustomDimensions']['postID']
        item['url'] = article_json['gaCustomDimensions']['location']
        item['title'] = article_json['gaCustomDimensions']['title']

        el = soup.find('time')
        if el:
            dt = datetime.fromisoformat(el['datetime'].replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(article_json['gaCustomDimensions']['datePublished'], '%Y%m%d').replace(tzinfo=timezone.utc)
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        el = soup.find('a', class_='author')
        if el:
            item['author'] = {"name": el.get_text().strip()}
        else:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['gaCustomDimensions']['displayAuthors']))

        item['tags'] = list(filter(None, article_json['gaCustomDimensions']['tags'].split('|')))

        el = soup.find(class_='heading_excerpt')
        if el:
            item['summary'] = el.get_text()

    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'html.parser')
        ld_json = None
        for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
            ld_json = json.loads(el.string)
            if ld_json.get('@type') and ld_json['@type'] == 'Article':
                break
            ld_json = None
        if not ld_json:
            logger.warning('unable to find ld+json data in ' + url)
            return None
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')

        item['id'] = ld_json['mainEntityOfPage']['@id']
        item['url'] = ld_json['mainEntityOfPage']['@id']
        item['title'] = ld_json['headline']

        dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

        authors = []
        for it in ld_json['author']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        if ld_json.get('keywords'):
            item['tags'] = ld_json['keywords'].copy()
        elif ld_json.get('articleSection'):
            if isinstance(ld_json['articleSection'], list):
                item['tags'] = ld_json['articleSection'].copy()
            elif isinstance(ld_json['articleSection'], str):
                item['tags'] = list(ld_json['articleSection'])

        if ld_json.get('description'):
            item['summary'] = ld_json['description']

        if ld_json.get('image'):
            item['_image'] = ld_json['image']['url']

    item['content_html'] = ''
    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_='heading_image')
    if el:
        item['_image'] = resize_image(el['data-img-url'])
        caption = re.sub('^"|"$', '', el['data-img-caption'])
        if caption == 'null':
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    el = soup.find(class_='w-rating-widget')
    if el:
        it = el.find(class_='rating-text')
        if it:
            item['content_html'] += '<h2>{}</h2>'.format(it.get_text().strip())

    body = soup.find(id='article-body')
    if body:
        if save_debug:
            utils.write_file(str(body), './debug/debug.html')
        for el in body.find_all(class_='emaki-custom-update'):
            new_html = ''
            for it in el.find_all(class_='update'):
                new_html += it.decode_contents()
            item['content_html'] += utils.add_blockquote(new_html)
            el.decompose()

        # Remove comment sections
        for el in body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        for el in body.find_all(class_=re.compile('ad-even|ad-odd|ad-zone|affiliate-sponsored|article-jumplink|article-table-contents')):
            el.decompose()

        for el in body.find_all(id='article-waypoint'):
            el.decompose()

        for el in body.find_all(class_='mobile-only'):
            # Usually duplicate section
            el.decompose()

        for el in body.find_all(class_=re.compile('next-single|related-single')):
            if el.parent and el.parent.name == 'p':
                el.parent.decompose()

        for el in body.find_all(class_=re.compile(r'content-block-(large|regular)')):
            el.unwrap()

        for el in body.find_all('blockquote', class_=False):
            #new_html = utils.add_pullquote(el.get_text().strip())
            new_html = utils.add_blockquote(el.get_text().strip())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='emaki-custom-block'):
            new_html = ''
            if 'emaki-custom-pullquote' in el['class']:
                it = el.find(class_='pullquote')
                if it:
                    new_html = utils.add_pullquote(it.decode_contents())
            elif 'emaki-custom-note' in el['class']:
                it = el.find(class_='note')
                if it:
                    new_html = utils.add_blockquote('<b>Note:</b>' + it.decode_contents())
            elif 'emaki-custom-tip' in el['class']:
                new_html = utils.add_blockquote('<b>Tip:</b>' + el.decode_contents())
            elif 'emaki-custom-warning' in el['class']:
                new_html = utils.add_blockquote('<span style="font-weight:bold; color:red;">Warning:</span>' + el.decode_contents(), border_color='red')
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled emaki-custom-block {} in {}'.format(el['class'], item['url']))

        for el in body.find_all(class_='w-rich'):
            new_html = ''
            if 'w-twitter' in el['class']:
                it = el.find(class_='twitter-tweet')
                if it.name == 'blockquote':
                    links = it.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                else:
                    new_html = utils.add_embed(utils.get_twitter_url(el['id']))
            elif 'w-youtube' in el['class']:
                new_html = utils.add_embed('https://www.youtube.com/embed/' + el['id'])
            elif 'w-instagram' in el['class']:
                it = el.find(class_='instagram-media')
                if it:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif 'w-spotify' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                else:
                    new_html = utils.add_embed(el['id'])
            elif 'w-soundcloud' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
            elif 'w-reddit' in el['class']:
                it = el.find('a')
                new_html = utils.add_embed(it['href'])
            elif 'w-twitch' in el['class']:
                it = soup.find('script', string=re.compile(r'window\.arrayOfEmbeds\["{}"\]'.format(el['id'])))
                if it:
                    m = re.search(r'src=\\"([^"]+)\\"', html.unescape(it.string))
                    if m:
                        #new_html = utils.add_embed('https://player.twitch.tv/?video=' + el['id'])
                        new_html = utils.add_embed(m.group(1).replace('\\/', '/'))
            elif 'w-play_store_app' in el['class']:
                new_html = add_play_store_app(el)

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))

        for el in body.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'div':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all(class_='display-card-quick-links'):
            el.decompose()

        for el in body.find_all(class_='w-display-card-list'):
            if 'specs' in el['class']:
                it = el.find('table')
                if it:
                    el.insert_after(it)
                    el.decompose()
                else:
                    logger.warning('unhandled display-card specs in ' + item['url'])
            else:
                for it in el.find_all('li', class_='display-card-element'):
                    it.unwrap()
                el.unwrap()

        for el in body.find_all(class_='display-card'):
            it = el.find(class_='w-display-card-info')
            if it and it.get_text().strip():
                new_html = '<div style="width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;">'
                it = el.find(class_='display-card-title')
                if it:
                    if it.a:
                        new_html += '<div style="text-align:center;"><a href="{}"><span style="font-size:1.3em; font-weight:bold;">{}</span></a></div>'.format(it.a['href'], it.get_text().strip())
                    else:
                        new_html += '<div style="text-align:center;"><span style="font-size:1.3em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
                it = el.find(class_='display-card-rating')
                if it:
                    new_html += '<div style="text-align:center;"><span style="font-size:1.5em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
                for it in body.find_all(class_='article__gallery'):
                    img = it.find(attrs={"data-img-url": re.compile(r'reco-badge', flags=re.I)})
                    if img:
                        new_html += '<div style="text-align:center;"><img src="{}" style="width:128px;"/></div>'.format(resize_image(img['data-img-url'], 128))
                        it.decompose()
                        break
                it = el.find(class_='w-img')
                if it:
                    new_html += '<div>{}</div>'.format(add_image(it))
                it = el.find(class_=re.compile(r'display-card-description'))
                if it:
                    new_html += '<p>{}</p>'.format(it.decode_contents())
                it = el.find(class_=re.compile(r'display-card-info'))
                if it:
                    new_html += '<div>{}</div>'.format(it.decode_contents())
                it = el.find(class_=re.compile(r'display-card-pros-cons'))
                if it:
                    new_html += str(it)
                it = el.find(class_=re.compile(r'display-card-link'))
                if it:
                    #new_html += '<div><ul>'
                    for link in it.find_all('a'):
                        #new_html += '<li><a href="{}">{}</a></li>'.format(utils.get_redirect_url(link['href']), link.get_text().strip())
                        new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#e01a4f; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(link['href']), link.get_text().strip())
                    #new_html += '</ul></div>'
                new_html += '</div>'
            else:
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;">'
                it = el.find(class_='display-card-badge')
                if it:
                    new_html += '<div style="flex:0 0 100%;"><span style="color:#e01a4f; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
                img_src = ''
                it = el.find('img')
                if it:
                    if it.get('src'):
                        img_src = resize_image(it['src'], 800)
                    elif it.get('data-img-url'):
                        img_src = resize_image(it['data-img-url'], 800)
                    else:
                        logger.warning('unhandled display-card image in ' + item['url'])
                if not img_src:
                    img_src = '{}/image?width=800&height=400&color=none'.format(config.server)
                new_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(img_src)
                new_html += '<div style="flex:2; min-width:256px; margin:auto;">'
                it = el.find(class_='display-card-title')
                if it:
                    if it.a:
                        new_html += '<div><a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a></div>'.format(it.a['href'], it.get_text().strip())
                    else:
                        new_html += '<div><span style="font-size:1.1em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
                it = el.find(class_='display-card-subtitle')
                if it:
                    new_html += '<div><i>{}</i></div>'.format(it.get_text().strip())
                it = el.find(class_='display-card-rating')
                if it:
                    new_html += '<div>Rating: {}</div>'.format(it.get_text().strip())
                it = el.find(class_=re.compile(r'display-card-description'))
                if it:
                    new_html += '<p>{}<p>'.format(it.get_text().strip())
                it = el.find(class_=re.compile(r'display-card-pros-cons'))
                if it:
                    new_html += it.decode_contents()
                it = el.find(class_=re.compile(r'display-card-link'))
                if it:
                    for link in it.find_all('a'):
                        new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#e01a4f; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(link['href']), link.get_text().strip())
                new_html += '</div></div><div>&nbsp;</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='w-review-item'):
            new_html = '<div style="width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;">'
            it = el.find(class_='review-item-title')
            if it:
                new_html += '<div style="text-align:center;"><span style="font-size:1.3em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
            it = el.find(class_=re.compile('rai?ting-number'))
            if it:
                new_html += '<div style="text-align:center;"><span style="font-size:1.5em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
            it = el.find(class_='w-review-item-img')
            if it:
                img = it.find(class_='body-img')
                new_html += '<div>{}</div>'.format(add_image(img))
            for it in el.find_all(class_='review-item-details'):
                new_html += '<div>{}</div>'.format(it.decode_contents())
            if el.find(class_='item-buy-btn'):
                for it in el.find_all(class_='item-buy-btn'):
                    new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#e01a4f; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(it['href']), it.get_text().strip())
            new_html += '</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='article__gallery'):
            new_html = ''
            for it in el.find_all(class_='gallery__images__item'):
                new_html += add_image(it, True)
            if not new_html:
                it = soup.find('script', string=re.compile(r'window\.arrayOfGalleries\["{}"\]'.format(el['id'])))
                if it:
                    s = html.unescape(it.string)
                    i = s.find('<')
                    j = s.rfind('>')
                    gallery_soup = BeautifulSoup(s[i:j+1].replace('\\"', '\"').replace('\\/', '/'), 'html.parser')
                    slides = []
                    for slide in gallery_soup.find_all(class_='gallery-main-img'):
                        if slide.source:
                            img_src = utils.clean_url(slide.source['srcset'])
                            if not img_src in slides:
                                slides.append(img_src)
                                new_html += add_image(slide)
                    it.decompose()
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled article__gallery in ' + item['url'])

        for el in body.find_all(class_='body-img'):
            new_html = add_image(el)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all('img', attrs={"alt": True}):
            if el.parent and el.parent.name == 'a':
                new_html = utils.add_image(resize_image(el['src']), link=el.parent['href'])
                if el.parent.parent and el.parent.parent.name == 'div':
                    it = el.parent.parent
                else:
                    it = el.parent
                new_el = BeautifulSoup(new_html, 'html.parser')
                it.insert_after(new_el)
                it.decompose()
            else:
                new_html = utils.add_image(resize_image(el['src']))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all('script'):
            new_html = ''
            m = re.search(r'window\.arrayOfEmbeds\[[^\]]+\] = \{\'([^\']+)\' : \'(.*?)\'\};\s*$', el.string, flags=re.S)
            if m:
                if m.group(1) == 'play_store_app':
                    it = BeautifulSoup(html.unescape(m.group(2).replace('\\', '')), 'html.parser')
                    new_html = add_play_store_app(it)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                #print(el)
                logger.warning('unhandled script ' + item['url'])

        for el in body.find_all('button'):
            el.decompose()

        for el in body.find_all(class_='table-container'):
            el.unwrap()

        for el in body.find_all(class_='gallery-lightbox'):
            el.decompose()

        for el in body.find_all('link', attrs={"rel": "stylesheet"}):
            el.decompose()

        for el in body.find_all('a', href=re.compile(r'^/')):
            el['href'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['href'])

        item['content_html'] += body.decode_contents()

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    item['content_html'] = re.sub(r'<div>(&nbsp;|\s)</div>\s*<div>(&nbsp;|\s)</div>', '<div>&nbsp;</div>', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
