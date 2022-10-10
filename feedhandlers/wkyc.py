import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    item = {}
    soup = BeautifulSoup(page_html, 'html.parser')
    article = soup.find('article')
    if article:
        item['id'] = article['data-article-id']
        item['url'] = article['data-url']
        item['title'] = article['data-title']

        el = soup.find('meta', attrs={"itemprop": "datePublished"})
        if el:
            # 9:42 AM EDT September 27, 2022
            dt_loc = datetime.strptime(el['content'].replace('EST', 'EDT'), '%I:%M %p EDT %B %d, %Y')
            tz_loc = pytz.timezone('US/Eastern')
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        el = soup.find('meta', attrs={"itemprop": "dateModified"})
        if el:
            dt_loc = datetime.strptime(el['content'].replace('EST', 'EDT'), '%I:%M %p EDT %B %d, %Y')
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_modified'] = dt.isoformat()

        item['author'] = {"name": article['data-author']}
        item['tags'] = article['data-keywords'].split(',')
        item['tags'] += article['data-watson-keywords'].split(',')

        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

        item['content_html'] = ''
        if article.get('data-abstract'):
            item['summary'] = article['data-abstract']
            item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

        el = soup.find(class_='article__lead-asset')
        if el:
            if el.find(class_='photo'):
                captions = []
                it = el.find(class_='photo__caption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                it = el.find(class_='photo__credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                img = el.find(class_='lazy-image__image')
                if img:
                    img_src = utils.image_from_srcset(img['data-srcset'], 1000)
                    item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
                else:
                    logger.warning('unhandled lead asset photo in ' + item['url'])
            else:
                it = el.find(class_='video')
                if it:
                    item['content_html'] += utils.add_video(it['data-stream'], 'application/x-mpegURL', it['data-thumbnail'], it['data-title'])
                else:
                    logger.warning('unhandled lead asset in ' + item['url'])

        article_body = article.find(class_='article__body')
        if article_body:
            for el in article_body.children:
                if el.name == 'div':
                    if 'article__section_type_text' in el['class']:
                        if el.find(class_='cms__embed-related-story'):
                            el.decompose()
                        elif re.search(r'<p><strong>(MORE HEADLINES|RELATED|SUBSCRIBE):', el.decode_contents()):
                            el.decompose()
                        else:
                            el.unwrap()
                    elif 'article__section_type_photo' in el['class']:
                        captions = []
                        it = el.find(class_='photo__caption')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        it = el.find(class_='photo__credit')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        img = el.find(class_='lazy-image__image')
                        if img:
                            img_src = utils.image_from_srcset(img['data-srcset'], 1000)
                            new_html = utils.add_image(img_src, ' | '.join(captions))
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            el.insert_after(new_el)
                            el.decompose()
                        else:
                            logger.warning('unhandled photo in ' + item['url'])

                    elif 'article__section_type_gallery' in el['class']:
                        it = el.find(class_='gallery')
                        new_html = '<h3>{}</h3>'.format(it['data-title'])
                        for it in el.find_all(class_='gallery__slide'):
                            captions = []
                            if it.get('data-caption'):
                                captions.append(it['data-caption'])
                            if it.get('data-credit'):
                                captions.append(it['data-credit'])
                            img_src = ''
                            img = it.find(class_='lazy-image__image')
                            if img:
                                img_src = utils.image_from_srcset(img['data-srcset'], 1000)
                            else:
                                img = it.find('img')
                                if img:
                                    img_src = utils.image_from_srcset(img['srcset'], 1000)
                            if img_src:
                                new_html += utils.add_image(img_src, ' | '.join(captions))
                            else:
                                logger.warning('unhandled gallery slide image in ' + item['url'])
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.insert_after(new_el)
                        el.decompose()

                    elif 'article__section_type_embed' in el['class']:
                        new_html = ''
                        it = el.find('iframe')
                        if it:
                            if 'count.gif' in it['src']:
                                el.decompose()
                            else:
                                new_html = utils.add_embed(it['src'])
                        elif el.find(id='fb-root'):
                            it = el.find('blockquote')
                            new_html = utils.add_embed(it['cite'])
                        else:
                            it = el.find('blockquote')
                            if it.get('class'):
                                if 'twitter-tweet' in it['class']:
                                    links = it.find_all('a')
                                    new_html = utils.add_embed(links[-1]['href'])
                                elif 'instagram-media' in it['class']:
                                    new_html = utils.add_embed(it['data-instgrm-permalink'])
                        if new_html:
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            el.insert_after(new_el)
                            el.decompose()
                        else:
                            logger.warning('unhandled article section embed in ' + item['url'])
                    elif 'article__section_type_ad' in el['class'] or 'related-stories' in el['class']:
                            el.decompose()
                    else:
                        logger.warning('unhandled article section {} in {}'.format(el['class'], item['url']))

        item['content_html'] += article_body.decode_contents()
    return item


def get_feed(args, save_debug=False):
    # https://www.wkyc.com/rss
    return rss.get_feed(args, save_debug, get_content)
