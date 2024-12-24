import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(e_image, width=1000):
    captions = []
    it = e_image.find('figcaption')
    if it:
        captions.append(it.decode_contents())
    it = e_image.find('cite')
    if it:
        captions.append(it.decode_contents())
    img_src = ''
    it = e_image.find('img')
    if it:
        if it.get('class') and 'c-dynamic-image' in it['class']:
            it = e_image.find(class_='e-image__image')
            if it and it.get('data-original'):
                img_src = it['data-original']
        else:
            if it.get('srcset'):
                img_src = utils.image_from_srcset(it['srcset'], width)
            elif it.get('src'):
                img_src = it['src']
    if not img_src:
        return ''
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('unable to find ld+json in ' + url)
        return None
    ld_json = json.loads(el.string)
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    article_json = None
    if isinstance(ld_json, dict):
        article_json = ld_json
    elif isinstance(ld_json, list):
        for it in ld_json:
            if it['@type'] == 'NewsArticle':
                article_json = it
                break
    if not article_json:
        logger.warning('unknown ld_json types in ' + url)
        return None

    item = {}
    item['id'] = article_json['mainEntityOfPage']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in article_json['author']]
    item['author'] = {
        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
    }

    if article_json.get('keywords'):
        item['tags'] = article_json['keywords'].copy()

    if article_json.get('thumbnailUrl'):
        item['image'] = article_json['thumbnailUrl']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    el = soup.find('p', class_='p-dek')
    if el:
        item['content_html'] += '<p><em>{}</em></p>'.format(el.get_text())
    elif item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find('figure', class_='e-image--hero')
    if not el:
        el = soup.find(class_='c-entry-hero__image')
    if el:
        new_html = add_image(el)
        if new_html:
            item['content_html'] += new_html
        else:
            logger.warning('unhandled e-image--hero in ' + item['url'])

    content = soup.find(class_='c-entry-content')
    if content:
        for el in content.find_all(class_='c-article-footer'):
            el.decompose()

        for el in content.find_all('div', recursive=False):
            new_html = ''
            if el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            elif el.q:
                new_html = utils.add_pullquote(el.q.decode_contents())
            elif el.get('class') and ('c-wide-block' in el['class'] or 'c-float-right' in el['class']):
                if el.find(class_='c-read-more'):
                    el.decompose()
                    continue
                elif el.find(class_='c-entry-sidebar'):
                    it = el.find(class_='c-entry-sidebar')
                    img = el.find('figure', class_='e-image')
                    if img:
                        new_html = '<div style="display:flex; flex-wrap:wrap; align-items:center; gap:0.5em; width:90%; margin:auto;">'
                        new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(add_image(img))
                        img.decompose()
                        new_html += '<div style="flex:2; min-width:256px;">{}</div>'.format(it.decode_contents())
                        new_html += '</div>'
                    else:
                        new_html = utils.add_blockquote(it.decode_contents())
                for it in el.find_all('figure', class_='e-image'):
                    new_html += add_image(it)
            elif el.find(class_='c-image-grid'):
                for it in el.find_all('figure', class_='e-image'):
                    new_html += add_image(it)
            elif el.find(class_='c-image-gallery'):
                for li in el.find_all('li'):
                    img_src = li.a['href']
                    captions = []
                    it = li.find(class_='c-image-gallery__thumb-title')
                    if it:
                        captions.append(it.get_text().strip())
                    it = li.find(class_='c-image-gallery__thumb-desc')
                    if it:
                        captions.append(it.get_text().strip())
                    new_html += utils.add_image(img_src, ' | '.join(captions))
            elif el.find(class_='c-imageslider'):
                it = el.find(class_='c-imageslider')
                data_json = json.loads(it['data-cdata'])
                new_html = '<figure style="margin:0; padding:0;"><div style="display:flex; flex-wrap:wrap; gap:0.5em;">'
                captions = []
                if data_json['image_left'].get('caption'):
                    captions.append(data_json['image_left']['caption'])
                if data_json['image_left'].get('credit'):
                    captions.append(data_json['image_left']['credit'])
                new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(data_json['image_left']['original_url'], ' | '.join(captions)))
                captions = []
                if data_json['image_right'].get('caption'):
                    captions.append(data_json['image_left']['caption'])
                if data_json['image_right'].get('credit'):
                    captions.append(data_json['image_right']['credit'])
                new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(utils.add_image(data_json['image_right']['original_url'], ' | '.join(captions)))
                new_html += '</div>'
                captions = []
                if data_json.get('caption'):
                    captions.append(data_json['caption'])
                if data_json.get('credit'):
                    captions.append(data_json['credit'])
                if captions:
                    new_html += '<figcaption><small>{}</small></figcaption>'.format(' | '.join(captions))
                new_html += '</figure>'
            elif el.find(attrs={"data-volume-uuid": True}):
                it = el.find(attrs={"data-volume-uuid": True})
                embed_html = utils.get_url_html('https://volume.vox-cdn.com/embed/{}?playing={}&placement={}&player_type={}&tracking={}'.format(it['data-volume-uuid'], it['data-volume-autoplay'], it['data-volume-placement'], it['data-volume-player-choice'], it['data-analytics-placement']))
                if embed_html:
                    m = re.search(r'var setup\s?=\s?({.*?});\n', embed_html)
                    if m:
                        video_json = json.loads(m.group(1))
                        if video_json['embed_assets']['chorus'].get('mp4_url'):
                            new_html = utils.add_video(video_json['embed_assets']['chorus']['mp4_url'], 'video/mp4', video_json['embed_assets']['chorus']['poster_url'], video_json['embed_assets']['chorus']['title'])
                        elif video_json['embed_assets']['chorus'].get('hls_url'):
                            new_html = utils.add_video(video_json['embed_assets']['chorus']['hls_url'], 'application/x-mpegURL', video_json['embed_assets']['chorus']['poster_url'], video_json['embed_assets']['chorus']['title'])
            elif el.find('blockquote', class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif el.find('blockquote', class_='instagram-media'):
                it = el.find('blockquote', class_='instagram-media')
                new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif el.find('section', class_='c-poll'):
                it = el.find('section', class_='c-poll')
                data_json = json.loads(it['data-cdata'])
                new_html = '<h3>Poll</h3><div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;"><h4>{}</h4><div>'.format(data_json['title'])
                for it in data_json['options']:
                    pct = int(it['votes'] / data_json['votes'] * 100)
                    if pct >= 50:
                        new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100 - pct, it['title'], pct)
                    else:
                        new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100 - pct, pct, it['title'], pct)
                new_html += '<div><small>{} votes</small></div></div>'.format(data_json['votes'])
            elif el.find('a', class_='p-button'):
                it = el.find('a', class_='p-button')
                if it['href'].startswith('/'):
                    link = '{}:{}{}'.format(split_url.scheme, split_url.netloc, it['href'])
                else:
                    link = it['href']
                new_html += '<div style="margin:1em; text-align:center;"><span style="padding:0.4em; background-color:#4f7177;"><a href="{}" style="color:white;">{}</a></span></div>'.format(link, it.get_text())
            elif el.find(class_='c-product-card__main'):
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                it = el.find('a', attrs={"data-analytics-link": "product-card:image"})
                if it:
                    img = it.find('img')
                    new_html += '<div style="flex:1; max-width:256px; min-width:160px;"><a href="{}"><img src="{}" style="width:100%;"/></a></div>'.format(it['href'], utils.image_from_srcset(img['srcset'], 400))
                new_html += '<div style="flex:1; min-width:256px;"><a href="{}">'
                it = el.find('a', attrs={"data-analytics-link": "product-card:title"})
                if it:
                    new_html += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(it['href'], it.get_text().strip())
                it = el.find('li', class_='c-product-card__main-price-discount')
                if it:
                    new_html += '<div><span style="font-size:1.1em; font-style:italic;">{}</span>'.format(it.get_text().strip())
                    it = el.find('li', class_='c-product-card__main-price-full')
                    if it:
                        new_html += ' <s>{}</s>'.format(it.get_text().strip())
                    new_html += '</div>'
                new_html += '<ul>'
                for it in el.find_all('li', class_='c-product-card__buttons'):
                    new_html += '<li><a href="{}">{}</a>'.format(it.a['href'], it.get_text().strip())
                new_html += '</ul></div></div>'
            elif el.find(class_='m-ad') or el.find('a', attrs={"data-analytics-link": "related-story"}) or el.find(class_='polygon-table-of-contents'):
                el.decompose()
                continue
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled div in ' + item['url'])

        for el in content.find_all('figure', class_='e-image'):
            new_html = add_image(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled e-image in ' + item['url'])

        for el in content.find_all('p', class_='p--has-dropcap'):
            new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(el), 1)
            new_html += '<span style="clear:left;"></span>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('blockquote', class_=False, recursive=False):
            if len(el.find_all('p')) == 1:
                new_html = utils.add_blockquote(el.p.decode_contents())
            else:
                new_html = utils.add_blockquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('aside'):
            if el.find(class_=['c-read-more', 'c-newsletter_signup_box']):
                el.decompose()
            else:
                logger.warning('unhandled aside in ' + item['url'])

        item['content_html'] += content.decode_contents()
    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
