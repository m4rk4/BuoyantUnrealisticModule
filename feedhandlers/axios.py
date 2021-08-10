import json, re
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlsplit

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  soup = BeautifulSoup(article_html, 'html.parser')

  item = {}
  #item['id']
  item['url'] = url
  item['title'] = soup.find('title').get_text()

  el = soup.find(attrs={"data-vars-sub-category": "author-line"})
  if el:
    item['author'] = {}
    item['author']['name'] = el.get_text()

  content_html = ''
  el = soup.find(id="maincontent")
  if el:
    del el['class']
    content_html += str(el)

  for story in soup.find_all(id=re.compile(r'story\d+')):
    content_html += '<hr width="80%" />'

    for div in story.next_sibling.children:
      div_class = div.get_attribute_list('class')
      # Heading
      if 'h6' in div_class:
        content_html += '<h3>{}</h3>'.format(div.get_text())
        continue

      # Story text
      if 'story-text' in div_class:
        del div['class']
        for el in div.find_all('figure'):
          img = el.find('amp-img')
          if img:
            figcaption = el.find('figcaption')
            if figcaption:
              caption = figcaption.get_text()
            else:
              caption = ''
            new_el = BeautifulSoup(utils.add_image(img['src'], caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        content_html += str(div)
        continue

      # Image
      figcaption = div.find('figcaption')
      if figcaption:
        img = div.find('amp-img')
        if img:
          content_html += utils.add_image(img['src'], figcaption.get_text())

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  # Assumes this is the newsletter feed from kill-the-newsletter.com
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(feed, file, indent=4)
  feed['home_page_url'] = 'https://www.axios.com/newsletters/'

  for feed_item in feed['items']:
    m = re.search('mailto:\?[^"]+(https[^"]+)', feed_item['content_html'])
    if m:
      split_url = urlsplit(unquote(m.group(1)))
      feed_item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    else:
      logger.warning('can not find real url for ' + feed_item['url'])
      continue

    if save_debug:
      logger.debug('getting content from ' + feed_item['url'])

    item = get_content(feed_item['url'], args, save_debug)
    if item:
      # Copy these items from the rss feed
      item_id = split_url.path.split('/')[-1]
      item['id'] = item_id[:-5] if item_id.endswith('.html') else item_id
      item['title'] = feed_item['title']
      item['date_published'] = feed_item['date_published']
      item['_timestamp'] = feed_item['_timestamp']
      item['_display_date'] = feed_item['_display_date']

      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed  