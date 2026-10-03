-- 模板:衍生作品导航 的手机版：手风琴。样式在 模板:衍生作品导航/styles.css。
-- 参数写法同 {{Navbox}}：groupN / listN，子层的 listN 里再写 {{#invoke:衍生作品导航|child|…}}；
-- 没有 groupN 的 listN 是这一层自己的条目，直接排在子组前面。
-- 当前页面所在的那条路径默认展开，其余收起；条目之间用 {{dot}} 隔开。
local p = {}

-- 一组的内容超过这么多字，它的子组就各自折叠；不超过的平铺成「小标题 + 列表」
local BIG = 500
-- {{dot}} 展开后的样子
local DOT = '&nbsp;<b>&middot;</b>'

local lang = mw.language.getContentLanguage()

-- text 里有没有指向 title 的链接。带 # 的章节链接不算：那是别的条目里的一节
local function linksTo(text, title)
	for target in text:gmatch('%[%[([^%[%]|#]+)[|%]]') do
		target = mw.text.trim((target:gsub('_', ' ')))
		if lang:ucfirst(target) == title then
			return true
		end
	end
	return false
end

-- 大致的可见字数：去掉标签、链接目标、strip marker
local function textLen(text)
	text = text:gsub('\127[^\127]*\127', '')
		:gsub('<[^>]*>', '')
		:gsub('%[%[[^%[%]|]*|', '')
		:gsub('%[https?://%S+', '')
		:gsub('&[#%w]+;', ' ')
		:gsub('[%[%]]', '')
	return mw.ustring.len(text)
end

-- 条目逐个包一层，窄屏上整项换行，分隔点跟着前一项走
local function items(list)
	local segs = mw.text.split(list, DOT, true)
	for i, seg in ipairs(segs) do
		segs[i] = '<span class="dnav-item">' .. mw.text.trim(seg)
			.. (i < #segs and '<span class="dnav-dot">&nbsp;·</span>' or '') .. '</span>'
	end
	return table.concat(segs, ' ')
end

local function entries(args)
	local nums = {}
	for k, v in pairs(args) do
		local n = type(k) == 'string' and k:match('^list(%d+)$')
		if n and mw.text.trim(v) ~= '' then
			nums[#nums + 1] = tonumber(n)
		end
	end
	table.sort(nums)
	local out = {}
	for i, n in ipairs(nums) do
		local group = mw.text.trim(args['group' .. n] or '')
		out[i] = { group = group ~= '' and group or nil, list = mw.text.trim(args['list' .. n]) }
	end
	return out
end

local function render(args, top)
	local title = mw.title.getCurrentTitle().prefixedText
	local list = entries(args)
	local size = 0
	for _, e in ipairs(list) do
		size = size + textLen(e.list)
	end
	local fold = top or size > BIG
	local out = {}
	for i, e in ipairs(list) do
		-- 子层 child 的输出原样放进来，普通列表才切条目
		local body = e.list:find('class="dnav-', 1, true) and e.list
			or '<div class="dnav-list">' .. items(e.list) .. '</div>'
		if not e.group then
			out[i] = body
		elseif fold then
			local open = linksTo(e.group, title) or linksTo(e.list, title)
			out[i] = '<div class="dnav-fold mw-collapsible' .. (open and '' or ' mw-collapsed') .. '">'
				.. '<div class="dnav-head mw-collapsible-toggle"><span class="dnav-name">' .. e.group .. '</span></div>'
				.. '<div class="dnav-body mw-collapsible-content">' .. body .. '</div></div>'
		else
			out[i] = '<div class="dnav-group"><div class="dnav-label">' .. e.group .. '</div>' .. body .. '</div>'
		end
	end
	return table.concat(out)
end

function p.main(frame)
	return '<div class="dnav nodesktop navigation-not-searchable">'
		.. '<div class="dnav-title">' .. (frame.args.title or '') .. '</div>'
		.. render(frame.args, true) .. '</div>'
end

function p.child(frame)
	return render(frame.args, false)
end

return p
