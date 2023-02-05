import html, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug=False):
  # https://seekingalpha.com/article/4474162-eastman-chemical-exposed-to-supply-shortages-especially-in-automotive?source=feed_symbol_EMN
  m = re.search(r'\/[^\/]+\/(\d+)-', url)
  if not m:
    logger.warning('unable to parse article id from ' + url)
    return None

  if '/news/' in url:
    api_url = 'https://seekingalpha.com/api/v3/news/{}?include=author%2CprimaryTickers.gics.sector%2CprimaryTickers.gics.sub_industry%2CsecondaryTickers.gics.sector%2CsecondaryTickers.gics.sub_industry%2CotherTags'.format(m.group(1))
  elif '/article/' in url:
    api_url = 'https://seekingalpha.com/api/v3/articles/{}?include=author%2CprimaryTickers.gics.sector%2CprimaryTickers.gics.sub_industry%2CsecondaryTickers.gics.sector%2CsecondaryTickers.gics.sub_industry%2CotherTags%2Cpresentations%2Cpresentations.slides%2Cauthor.authorResearch%2Cco_authors%2CpromotedService%2Csentiments'.format(m.group(1))
  elif '/pr/' in url:
    api_url = 'https://seekingalpha.com/api/v3/press_releases/{}?include=acquireService%2CprimaryTickers'.format(m.group(1))

  article_json = utils.get_url_json(api_url)
  if not article_json:
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  item = {}
  item['id'] = article_json['data']['id']
  item['url'] = article_json['data']['links']['canonical']
  item['title'] = article_json['data']['attributes']['title']

  dt = datetime.fromisoformat(article_json['data']['attributes']['publishOn']).astimezone(timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  if article_json['data']['attributes'].get('lastModified'):
    dt = datetime.fromisoformat(article_json['data']['attributes']['lastModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

  author = ''
  tags = []
  presentation = ''
  for it in article_json['included']:
    if it['type'] == 'newsAuthorUser' or it['type'] == 'author':
      author = it['attributes']['nick']
    elif it['type'] == 'acquireService':
      author = it['attributes']['providerName']
    elif it['type'] == 'tag':
      tags.append(it['attributes']['name'])
    elif it['type'] == 'presentationSlide':
      presentation += '<h3>{}</h3>'.format(it['attributes']['title'])
      presentation += utils.add_image(it['links']['self'])
      presentation += '<p>{}</p>'.format(it['attributes']['content'])

  if author:
    item['author'] = {}
    item['author']['name'] = author
  if tags:
    item['tags'] = tags.copy()

  if article_json['data']['links'].get('uriImage'):
    item['_image'] = article_json['data']['links']['uriImage']

  item['summary'] = article_json['meta']['page']['description']

  soup = BeautifulSoup(article_json['data']['attributes']['content'], 'html.parser')

  if presentation:
    el = soup.find(class_='sa-presentation')
    if el:
      el.insert_after(BeautifulSoup(presentation, 'html.parser'))
      el.decompose()
    else:
      logger.warning('unknown presentation slides ' + url)

  for el in soup.find_all(class_=['adPlaceHolder', 'wsb_ad']):
    el.decompose()

  for el in soup.find_all(class_=['answer', 'question', 'ticker-hover-wrapper']):
    el.unwrap()

  for el in soup.find_all('div', class_=['wsb_wrapper', 'wsb_main', 'wsb_section', 'wsb_mb', 'wsb_pt']):
    el.unwrap()

  for el in soup.find_all('p', class_='wsb_pb'):
    el.attrs = {}
    if el.parent and el.parent.name == 'span':
      el.parent.unwrap()
    if not el.get_text().strip():
      el.decompose()

  for el in soup.find_all('figure', class_='sa-ycharts'):
    new_html = utils.add_image(el.img['src'], el.get_text())
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all('figure', class_='getty-figure'):
    if el.img:
      img_src = el.img['src']
    elif el.source:
      m = re.search(r'https:[^\s,]+', el.source['srcset'])
      img_src = m.group(0)
    m = re.search(r'\/getty_images\/(\d+)\/', img_src)
    if m:
      img_src = 'https://static.seekingalpha.com/cdn/s3/uploads/getty_images/{0}/large_image_{0}.jpg'.format(m.group(1))
      if el.figcaption:
        caption = utils.bs_get_inner_html(el.figcaption.get_text())
      else:
        caption = ''
      new_html = utils.add_image(img_src, caption)
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in soup.find_all('img'):
    if el.parent:
      if el.parent.name == 'figure':
        continue
      else:
        p = None
        if el.parent.name == 'a':
          img_src = el.parent['href']
          if el.parent.parent:
            if el.parent.parent.name == 'p':
              p = el.parent.parent
            elif el.parent.parent.name == 'span':
              if el.parent.parent.parent:
                if el.parent.parent.parent.name == 'p':
                  p = el.parent.parent.parent
        else:
          img_src = el['src']
          if el.parent.name == 'p':
            p = el.parent
        caption = ''
        if p:
          c = p.find_next_sibling()
          if c:
            caption = ''
            if re.search(r'Source:|Figure \d', c.get_text()) or re.search('^<p><em>.*<\/em><\/p>$', str(c)):
              caption = utils.bs_get_inner_html(c)
              c.decompose()
        else:
          p = el
        new_html = utils.add_image(img_src, caption)
        p.insert_after(BeautifulSoup(new_html, 'html.parser'))
        p.decompose()

  for el in soup.find_all('span', class_='table-responsive'):
    el.name = 'figure'
    el.attrs = {}
    el['style'] = 'font-size:0.9em;'
    el.table['style'] = 'border-collapse:collapse;'
    for it in el.table.find_all('tr'):
      it['style'] = 'border-bottom:1pt solid black;'
    for it in el.table.find_all('td'):
      it['style'] = 'padding-right:1em;'
    if el.colgroup:
      el.colgroup.decompose()
    it = el.find_next_sibling()
    if it and re.search(r'Sources?:|Figure \d', it.get_text()):
      new_html = '<figcaption><small>{}</small></figcaption>'.format(utils.bs_get_inner_html(it))
      el.table.insert_after(BeautifulSoup(new_html, 'html.parser'))
      it.decompose()

  for el in soup.find_all('blockquote'):
    quote = ''
    for it in el.find_all('p'):
      if it.get_text().strip():
        if quote:
          quote += '<br/><br/>'
        quote += utils.bs_get_inner_html(it)
    if not quote:
      quote = utils.bs_get_inner_html(el)
    new_html = utils.add_blockquote(quote)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all(class_=['b', 'bold', 'wsb_bold']):
    el.attrs = {}
    el['style'] = 'font-weight:bold;'

  for el in soup.find_all(class_=['i', 'italic', 'wsb_italic']):
    el.attrs = {}
    el['style'] = 'font-style:italic;'

  for el in soup.find_all(class_='sa-embed'):
    if 'seekingalpha.com/embed' in el.iframe['src']:
      embed_html = utils.get_url_html(el.iframe['src'])
      m = re.search(r'src="([^"]+)"', embed_html)
      if m:
        if 'embedly.com' in m.group(1):
          m = re.search(r'src=(.*)', m.group(1))
          if m:
            p = dict(parse_qs(urlsplit(unquote_plus(html.unescape(m.group(1)))).query))
            if p.get('url'):
              new_html = utils.add_embed(p['url'][0])
              el.insert_after(BeautifulSoup(new_html, 'html.parser'))
              el.decompose()

  for el in soup.find_all('a', href=re.compile(r'https:\/\/salpha\.clickmeter\.com\/')):
    el['href'] = utils.get_redirect_url(el['href'])

  item['content_html'] = ''
  #if item.get('_image'):
  #  item['content_html'] = utils.add_image(item['_image'])
  if article_json['data']['attributes'].get('summary'):
    item['content_html'] += '<h2>Summary</h2><ul>'
    for it in article_json['data']['attributes']['summary']:
      item['content_html'] += '<li>{}</li>'.format(it)
    item['content_html'] += '</ul>'
  item['content_html'] += str(soup)
  return item

def get_feed(url, args, site_json, save_debug):
  # Company RSS: https://seekingalpha.com/api/sa/combined/TSLA.xml
  if args['url'].endswith('.xml'):
    return rss.get_feed(url, args, site_json, save_debug, get_content)

  # Trending news: https://seekingalpha.com/api/v3/news/trending?filter[category]=market-news%3A%3Aall&page[number]=1&page[size]=12
  # Trending articles: https://seekingalpha.com/api/v3/articles/trending?filter[category]=latest-articles&include=author&page[number]=1&page[size]=12
  # Latest articles: https://seekingalpha.com/api/v3/articles?filter[category]=latest-articles&include=author%2CprimaryTickers%2CsecondaryTickers&page[number]=1&page[size]=12
  # Editors picks: https://seekingalpha.com/api/v3/articles?filter[category]=editors-picks&include=author%2CprimaryTickers%2CsecondaryTickers&page[number]=1&page[size]=12
  # Notable calls & insights: https://seekingalpha.com/api/v3/news?filter[category]=market-news%3A%3Anotable-calls-insights&include=author%2CprimaryTickers%2CsecondaryTickers%2CotherTags&page[number]=1&page[size]=12
  # Stock ideas: https://seekingalpha.com/api/v3/articles?filter[category]=stock-ideas&include=author%2CprimaryTickers%2CsecondaryTickers&page[number]=1&page[size]=12

  feed_json = utils.get_url_json(args['url'])
  if not feed_json:
    return None
  if save_debug:
    utils.write_file(feed_json, './debug/feed.json')

  feed_items = []
  for article in feed_json['data']:
    article_url = 'https://seekingalpha.com' + article['links']['self']
    if save_debug:
      logger.debug('getting content for ' + article_url)
    item = get_content(article_url, args, site_json, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        feed_items.append(item)

  feed = utils.init_jsonfeed(args)
  feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
  return feed