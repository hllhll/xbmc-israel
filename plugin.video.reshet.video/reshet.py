# -*- coding: utf-8 -*-

"""
    Plugin for streaming video content from Reshet VOD based on Android
    
    Copyright (c) 2010-2012 Shai Bentin.
    All rights reserved.  Unpublished -- rights reserved

    Use of a copyright notice is precautionary only, and does
    not imply publication or disclosure.
 
    Licensed under Eclipse Public License, Version 1.0
    Initial Developer: Shai Bentin.

"""

"""
    Around march 2017, It looks like reshet switched (at least partially) from API-Based approach
    to webview-based approach, this resulted that no episodes could be watched.
    I Have made some work to switch over to feed off the webview content of the app, which is essentially the SAME as the web Version

    I Guess reshet/appcaster would eventually block all API calls,
    but for the time-beeing, I'll fill in only the places where they return no result

    Hillel (and Daniel) Chimowicz, 2017
"""
import urllib, urllib2, re, os, sys, unicodedata, random, json
import xbmcaddon, xbmc, xbmcplugin, xbmcgui
from bs4 import BeautifulSoup
import resources.m3u8 as m3u8

##General vars
__plugin__ = "Reshet"
__author__ = "Shai Bentin"

__settings__ = xbmcaddon.Addon(id='plugin.video.reshet.video')
__language__ = __settings__.getLocalizedString
__PLUGIN_PATH__ = __settings__.getAddonInfo('path')
__DEBUG__       = __settings__.getSetting('DEBUG') == 'true'

LIB_PATH = xbmc.translatePath( os.path.join( __PLUGIN_PATH__, 'resources', 'appCaster' ) )
M3U8_PATH = xbmc.translatePath( os.path.join( __PLUGIN_PATH__, 'resources', 'm3u8' ) )
sys.path.append (LIB_PATH)
sys.path.append (M3U8_PATH)

__properties = {'pKey':'a25129723d425516a51fe2910c', 'accountId': '32', 'broadcasterId':'1', 'bundle':'com.applicaster.iReshetandroid', 'bucketId':'507fe8f13b35016f91033bfa'}
import APCategoryLoader, APAccountLoader, APBroadcaster, APCategoryList, APItemLoader, APChannel, APChannelLoader
import APEpgLoader, APVodItem, APCategory, APExtensions
from DQAPCategory import DQAPCategory
from DQAPVodItem import DQAPVodItem

rootCategoryId = ''

def getMainCategoryList():
    global rootCategoryId
    ## Get the account details
    ## account
    accountLoader = APAccountLoader.APAccountLoader(__properties)
    jsonAccountDictionary = accountLoader.loadURL()    
    xbmc.log('accountURL --> %s' % (accountLoader.getQuery()), xbmc.LOGDEBUG)
    
    # get programs category
    rootCategoryId = ''
    
    if '' == rootCategoryId:
        ## broadcaster and main category from previous incarnation of the plugin
        broadcaster = APBroadcaster.APBroadcaster(__properties['broadcasterId'], jsonAccountDictionary["account"]["broadcasters"])
        xbmc.log('Main Category --> %s' % (broadcaster.getRootCategory()), xbmc.LOGDEBUG)
        rootCategoryId = broadcaster.getRootCategory()
    
    # get the main categories list
    getCategory(rootCategoryId)

def getLinkUrlFromReshetScheme(reshetUrl):
    paramParts = reshetUrl.split('?')
    if len(paramParts)<=1:
        return None
    paramParts = paramParts[1].split('&')
    # find linkUrl
    for item in paramParts:
        parts = item.split('linkUrl=')
        if(len(parts)>1):
            return urllib.unquote_plus( parts[1] )
    return None


def urlEncodeNonAscii(b):
    return re.sub('[\x80-\xFF]', lambda c: '%%%02x' % ord(c.group(0)), b)


def getPageDataQueryJsonObject(url):

    xbmc.log("getPageDataQueryJsonObject url = " + url, xbmc.LOGDEBUG)
    response = urllib2.urlopen(urlEncodeNonAscii(url).replace(" ", "+"))

    unicode_text = response.read().decode('utf-8')

    parsed_html = BeautifulSoup(unicode_text,"html.parser")
    # we need to find the script element that has data_query
    #for script in html.iter('script'):

    patternJsonDataScript = re.compile(ur'data_query = ', re.UNICODE)
    patternJson = re.compile(ur'\{.*\}', re.UNICODE)

    for script in parsed_html.find_all('script'):
        str = '' if (script.string is None) else script.string.encode('utf-8')
     
        if patternJsonDataScript.search(str) is not None:
            jsStruct = patternJson.search(str)
            if jsStruct is None:
                #error
                xbmc.log('getPageDataQueryJsonObject() Could not find data_query json', xbmc.LOGDEBUG) 
                return None
                #quit
            jsonStr = jsStruct.group(0)
            data = json.loads(jsonStr)
            break
    return data

def getCategory(categoryId, categoryLink = None):
    # get the main categories list

    # I.E the first time it would be all shows list,
    # Next time a category is a specific show
    # Main category list works ok, continue as `classic`-api-based approach

    if rootCategoryId != categoryId and categoryLink is not None and categoryLink!='':
        xbmc.log("getCategory not root category. catId=" + str(categoryId) + " Link?=" + categoryLink)
        # not "all shows" menu
        # use the new scraping method
        categoryWebUrl = getLinkUrlFromReshetScheme(categoryLink)
        if categoryWebUrl is None:
            categoryWebUrl = categoryLink
        xbmc.log("Loading reshet url = " + categoryWebUrl)
        data = getPageDataQueryJsonObject(categoryWebUrl)
        # We might be in: 1) a subcat - i.e. other stuff, intervies, episodes
        # or we in 2) the root of the category, where the above list would show
        
        # Push sub-cats
        sections = data['Content']['PageGrid']
        for section in sections:
            xbmc.log('adding item view DQAPCategory...')
            my_category = DQAPCategory(section['GridTitle'])
            addCategoryView(my_category)

            # also push videos if available
            posts = section['Posts']
            for video in posts:
                if video['video'] is not None:
                    xbmc.log('adding item view DQAPVodItem...', xbmc.LOGDEBUG)
                    item = DQAPVodItem(video)
                    addItemView(item)
        return

    # "all shows" menu, Need to make sure that the link for the different shows, is available for this next getCategory function call
    categoryLoader = APCategoryLoader.APCategoryLoader(__properties, categoryId)
    xbmc.log('CategoryURL --> %s' % (categoryLoader.getQuery()), xbmc.LOGDEBUG)
    jsonCategoryDictionary= categoryLoader.loadURL()
    categories = APCategoryList.APCategoryList(jsonCategoryDictionary["category"])

    # detect all shows and expand it. patchy for now, we may remove this later to support more features
    if (categories.hasSubCategories()):
        allCategory = categories.getSubCategories()[0]
	name = allCategory.getName()
	if name == 'All Shows':
	    # reload category list
	    categoryLoader = APCategoryLoader.APCategoryLoader(__properties, allCategory.getId())
	    jsonCategoryDictionary = categoryLoader.loadURL()
	    categories = APCategoryList.APCategoryList(jsonCategoryDictionary["category"])
 
    if (categories.hasSubCategories()):
        for category in categories.getSubCategories():
            if category.getId() not in ['36', '3103']: # omit the non video stuff
                addCategoryView(category)
    elif (categories.hasVideoitems()):
        for item in categories.getVodItems():
            xbmc.log('adding item view APVodItem...')
            addItemView(item)
        xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
        xbmc.executebuiltin("Container.SetViewMode(504)")
            
def getItem(itemId, link = None):
    itemLoader = APItemLoader.APItemLoader(__properties, itemId)
    xbmc.log('ItemURL --> %s' % (itemLoader.getQuery()), xbmc.LOGDEBUG)
    jsonItemDictionary = itemLoader.loadURL()
    if link is not None:
        xbmc.log('getItem to play using link ' + link, xbmc.LOGDEBUG)
        item = DQAPVodItem({})
        playMovie(item, link)
    else:
        # get the item and load it's movie
        item = APVodItem.APVodItem(jsonItemDictionary["vod_item"])
    playMovie(item, link)
    
          
def addCategoryView(category):
    xbmc.log('category --> %s' % (category.getId()), xbmc.LOGDEBUG)
    _url = sys.argv[0] + "?category=" + category.getId()
    if category.getLink() is not None and category.getLink()!='':
        _url = _url + "&link=" + urllib.quote(category.getLink())
    xbmc.log('Category link ' + _url)

    title = category.getTitle().encode('UTF-8')
    summary = category.getDescription().encode('UTF-8')
    thumbnail = category.getThumbnail()
    fanart = category.getFanartImage()
    
    liz = xbmcgui.ListItem(title, iconImage = thumbnail, thumbnailImage = thumbnail)
    liz.setInfo(type="Video", infoLabels={ "Title": urllib.unquote(title), "Plot": urllib.unquote(summary)})
    if not fanart == '':
        liz.setProperty("Fanart_Image", fanart)
    return xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=_url, listitem=liz, isFolder=True)

def addItemView(item):
    xbmc.log('item --> %s' % (item.getId()), xbmc.LOGDEBUG)
    _url = sys.argv[0] + "?item=" + item.getId()
    if item.getStreamUrl() is not None and item.getStreamUrl()!='':
        _url = _url + "&itemlink=" + urllib.quote(item.getStreamUrl())

    title = item.getTitle().encode('UTF-8')
    summary = item.getDescription().encode('UTF-8')
    thumbnail = item.getThumbnail()
    season = item.getSeasonName()
    airdate = item.getAirDate()
	
    if season is not None:
		season = urllib.unquote(season)
    listItem = xbmcgui.ListItem(title, iconImage = thumbnail, thumbnailImage = thumbnail)
    listItem.setInfo(type="Video", infoLabels={ "Title": urllib.unquote(title), "Plot": urllib.unquote(summary), "Season": season, "Aired": urllib.unquote(airdate)})
    listItem.setProperty("Fanart_Image", thumbnail)
    listItem.setProperty('IsPlayable', 'true')
    return xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=_url, listitem=listItem, isFolder=False)

def cleanCookie(cookieStr):
    cookies = cookieStr.split(';')
    authCookie = ''
    for cookie in cookies:
        pos = cookie.lower().find('hdea_l')
        if pos >= 0:
            authCookie = authCookie + cookie[pos:] + '; '
        pos = cookie.lower().find('hdea_s')
        if pos >= 0:
            authCookie = authCookie + cookie[pos:] + '; '
    return authCookie


def getHLSPlaylist(url, bFindBest=True):
    '''
    given a URL, determine if it's an HTTP live streaming playlist and find the best segments to use (only if we dont trust ffmpeg)
    '''
    # make sure it's a playlist at all, safe to rsplit
    urlPath = url.rsplit('?')[0]
    if False == urlPath.endswith('m3u8'):
        return url

    isHls = True

    xbmc.log("getHLSPlaylist url=" + url, xbmc.LOGDEBUG)
    # obtain the playlist and save any cookie that might be set. urlllib will join Set-Cookie headers based on RFC (one of them :)
    req = urllib2.Request(url)
    response = urllib2.urlopen(req)
    playlistStr = response.read()
    #hls_cookie = cleanCookie(response.info().getheader('Set-Cookie'))
    response.close()

    # parse m3u8 to find the best bitrate segments. if not variant, return original URL
    urlPath = url
    if bFindBest == True:
        variant_m3u8 = m3u8.loads(playlistStr)
        if True == variant_m3u8.is_variant:
            maxBW=0
            maxIdx=0
            for i, playlist in enumerate(variant_m3u8.playlists):
                bw = int(playlist.stream_info.bandwidth)
            if bw > maxBW:
                maxBW = bw
                maxIdx = i
            playlist = variant_m3u8.playlists[maxIdx]

            # build segments URL
            # TODO: Pass this to real url parsing engine, since it might be relative and might be absalute
            
            #urlPath = urlPath.rsplit('/', 1)[0] # removes the filename
            #urlPath = urlPath + '/' + playlist.uri
            return playlist.uri

        return urlPath


def playMovie(item, url = None):  
    DelCookies()
    _url = url
    if url is None:
        _url = item.getStreamUrl()

    _url = getHLSPlaylist(_url, True)

    _hls_cookie = item.getHLSCookie()
    xbmc.log('vod_item --> %s' % (item.getId()), xbmc.LOGDEBUG)
    xbmc.log('playable _url --> %s' % (_url), xbmc.LOGDEBUG)
    title = item.getTitle().encode('UTF-8')
    summary = item.getDescription().encode('UTF-8')
    thumbnail = item.getThumbnail()
    
    # falsify a user agent
    _user_agent = '|User-Agent=' + urllib.quote_plus('%D7%A8%D7%A9%D7%AA/24.8.11.46 CFNetwork/672.0.2')
    _dummyHeader = '&Accept-Language=en-US'

    # add a specific cookie, if needed (not normally)
    _cookie = ''
    if '' != _hls_cookie:
        _cookie = '&Cookie=' + urllib.quote_plus(_hls_cookie)

    listItem = xbmcgui.ListItem(title, iconImage = thumbnail, thumbnailImage = thumbnail, path=_url + _user_agent + _dummyHeader)
    listItem.setInfo(type='Video', infoLabels={ "Title": urllib.unquote(title), "Plot": urllib.unquote(summary)})
    listItem.setProperty('IsPlayable', 'true')

    # Gotham properly probes the mime type now, no need to do anything special
    xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listItem)

def DelCookies():
	try:
		tempDir = xbmc.translatePath('special://temp/').decode("utf-8")
		tempCookies = os.path.join(tempDir, 'cookies.dat')
		if os.path.isfile(tempCookies):
			os.unlink(tempCookies)
	except Exception as ex:
		print ex

def getParams(arg):
    param=[]
    paramstring=arg
    if len(paramstring)>=2:
        params=arg
        cleanedparams=params.replace('?','')
        if (params[len(params)-1]=='/'):
            params=params[0:len(params)-2]
        pairsofparams=cleanedparams.split('&')
        param={}
        for i in range(len(pairsofparams)):
            splitparams={}
            splitparams=pairsofparams[i].split('=')
            if (len(splitparams))==2:    
                param[splitparams[0]]=splitparams[1]
                            
    return param

# manage a random deviceId (if not already saved)
deviceId = __settings__.getSetting(id = 'deviceId')
if None == deviceId or '' == deviceId:
    rand1 = int((random.random() * 8999) + 1000)
    rand2 = int((random.random() * 8999) + 1000)
    rand3 = int((random.random() * 8999) + 1000)

    deviceId = str(rand1) + str(rand2) + str(rand3) 
    
    __settings__.setSetting(id = 'deviceId', value = deviceId)

__properties['deviceId'] = deviceId
xbmc.log('*****: deviceId --> %s' % (__properties['deviceId']), xbmc.LOGDEBUG)


# if we dont have a unique user ID and token yet, make it so
uuid = ''
token = ''
uuid = __settings__.getSetting(id = 'UUID')
token = __settings__.getSetting(id = 'deviceAuthToken')
xbmc.log('*****: UUID from settings --> %s, auth token from settings --> %s' % (uuid, token), xbmc.LOGDEBUG)
if None == uuid or '' == uuid:
    accountLoader = APAccountLoader.APAccountLoader(__properties)
    uuidDict = accountLoader.loadURL()
    uuid = uuidDict['id']
    token = uuidDict['token']
    if None != id and '' != id:
        __settings__.setSetting(id = 'UUID', value = uuid)
    if None != token and '' != token:
        __settings__.setSetting(id = 'deviceAuthToken', value = token)

__properties['UUID'] = uuid
__properties['deviceAuthToken'] = token
xbmc.log('*****: final UUID --> %s, final auth token --> %s' % (uuid, token), xbmc.LOGDEBUG)

params = getParams(sys.argv[2])
categoryId = None
categoryLink = None
itemId = None
itemlink = None

try:
    categoryId=urllib.unquote_plus(params["category"])
except:
    pass
try:
    itemId=urllib.unquote_plus(params["item"])
except:
    pass
try:
    categoryLink=urllib.unquote_plus(params["link"])
    #xbmc.log('Fetched link ' + categoryLink)
except:
    pass
try:
    itemlink=urllib.unquote_plus(params["itemlink"])
    #xbmc.log('Fetched item link ' + itemlink)
except:
    pass


if None == categoryId and None == itemId:
    getMainCategoryList()
elif None != categoryId:
    getCategory(categoryId, categoryLink)
elif None != itemId:
    getItem(itemId, itemlink) # Just a hack to pass the link, not bothering creating another argument+var...
            
xbmcplugin.setPluginFanart(int(sys.argv[1]),xbmc.translatePath( os.path.join( __PLUGIN_PATH__, "fanart.jpg") ))
xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=False)