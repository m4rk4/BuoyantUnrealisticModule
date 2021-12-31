import html, json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
  if '/__origami/' in img_src:
    return re.sub(r'width=\d+', 'width={}'.format(width), img_src)
  return 'https://www.ft.com/__origami/service/image/v2/images/raw/{}?source=google-amp&fit=scale-down&width={}'.format(quote_plus(img_src), width)

def get_content(url, args, save_debug=False):
  if url.startswith('://'):
    url = url.replace('://', 'https://www.ft.com')

  if '/reports/' in url:
    # skip
    return None
  elif '/video/' in url:
    article_url = url
  else:
    article_url = url.replace('www.ft.com', 'amp.ft.com')

  article_html = utils.get_url_html(article_url, user_agent='googlebot')
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  soup = BeautifulSoup(article_html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if not el:
    logger.warning('unable to find ld+json data in ' + url)
    return None
  try:
    ld_json = json.loads(el.string)
  except:
    logger.warning('unable to load ld+json data in ' + url)
    return None
  if save_debug:
    utils.write_file(ld_json, './debug/debug.json')

  item = {}
  item['id'] = url

  if ld_json.get('mainEntityofPage'):
    item['url'] = ld_json['mainEntityofPage']
  elif ld_json.get('url'):
    item['url'] = ld_json['url']
  else:
    item['url'] = url

  if ld_json.get('headline'):
    item['title'] = ld_json['headline']
  elif ld_json.get('name'):
    item['title'] = ld_json['name']

  dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  if ld_json.get('dateModified'):
    dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

  item['author'] = {}
  if ld_json.get('author') and ld_json['author'].get('name'):
    item['author']['name'] = ld_json['author']['name']
  elif ld_json.get('publisher') and ld_json['publisher'].get('name'):
    item['author']['name'] = ld_json['publisher']['name']
  else:
    item['author']['name'] = 'Financial Times'

  if ld_json.get('description'):
    item['summary'] = ld_json['description']

  item['content_html'] = ''
  if ld_json.get('image'):
    item['_image'] = ld_json['image']['url']
    item['content_html'] += utils.add_image(resize_image(item['_image']))

  if ld_json['@type'] == 'VideoObject':
    item['_video'] = ld_json['contentUrl']
    caption = '<a href="{}">{}</a>. {}'.format(item['url'], item['title'], item['summary'])
    item['content_html'] += utils.add_video(ld_json['contentUrl'], 'video/mp4', ld_json['thumbnailUrl'], caption)
    if args and 'embed' in args:
      return item
    el = soup.find(class_='video__standfirst')
    if el:
      item['content_html'] += str(el)
    el = soup.find(class_='video__byline')
    if el:
      item['content_html'] += str(el)
    el = soup.find(class_='video__transcript__text')
    if el:
      item['content_html'] += '<hr/><h3>Transcript</h3>' + str(el)
    return item

  article = soup.find(class_='article-body')
  if not article:
    logger.warning('unable to find article-body content in ' + url)
    return item
  del article['class']

  for el in article.find_all(class_=['ad-container', 'article__copyright-notice', 'n-content-recommended']):
    el.decompose()

  for el in article.find_all(class_=re.compile(r'n-content-heading-\d')):
    del el['class']

  for el in article.find_all('figure', class_=['n-content-picture', 'article-image']):
    if el.figcaption:
      caption = utils.bs_get_inner_html(el.figcaption)
    else:
      caption = ''
    img = el.find('amp-img')
    new_html = utils.add_image(resize_image(img['src']), caption)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in article.find_all(class_='n-content-video'):
    new_embed = get_content(el.a['href'], {"embed": True}, save_debug)
    if new_embed:
      el.insert_after(BeautifulSoup(new_embed['content_html'], 'html.parser'))
      el.decompose()

  for el in article.find_all(class_='n-content-layout'):
    if el.find('a', href=re.compile(r'https:\/\/ep\.ft\.com\/newsletters\/subscribe\?||https:\/\/ep\.ft\.com\/newsletters/[^\/]+\/subscribe')) or el.find(id=re.compile(r'recommended-newsletters-for-you')):
      el.decompose()

  for el in article.find_all('blockquote'):
    new_html = ''
    if el.get('class') and 'article__quote--pull-quote' in el['class']:
      quote = ''
      for it in el.find_all('p'):
        quote += utils.bs_get_inner_html(it)
      if el.footer:
        author = el.footer.get_text().strip()
      else:
        author = ''
      new_html = utils.add_pullquote(quote, author)
    else:
      for it in el.find_all('a', attrs={"data-vars-link-destination": True}):
        if 'twitter.com' in it['data-vars-link-destination']:
          new_html = utils.add_embed(it['data-vars-link-destination'])
          break
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  item['content_html'] += str(article)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)