from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from feedhandlers import rss
import utils

def get_content_html(url, args, post_item=None, add_title=False, save_debug=False):
  mercury = utils.get_url_json('https://mercuryparser.m4rk4.repl.co/?url=' + quote_plus(url))
  html = ''
  if mercury:
    if save_debug:
      with open('./debug/debug.html', 'w', encoding='utf-8') as f:
        f.write(html)
      
    if add_title:
      html += '<h2>{}</h2>'.format(mercury['title'])

    if 'addledeimage' in args:
      html += utils.add_image(mercury['lead_image_url'])

    if 'removeimage' in args:
      if post_item:
        del post_item['image']

    html += mercury['content']
    soup = BeautifulSoup(html, 'html.parser')
    for el in soup.find_all('img'):
      el['width'] = '100%'
      if el.has_attr('height'):
        del el['height']
    for el in soup.find_all('figcaption'):
      if el.string:
        el.string.wrap(soup.new_tag('small'))
    html += str(soup)
  return html

def get_feed(args):
  feed = rss.get_feed(args)
  for item in feed['items']:
    item['content_html'] = get_content_html(item['url'], args, item)
  return feed
