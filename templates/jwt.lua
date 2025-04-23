local auth_str=ngx.var.http_authorization
if not auth_str or not auth_str:find("Bearer ") == 1 then
    return
end
local jwt_token = auth_str:sub(8)
local jwt_parts = {}
for part in jwt_token:gmatch("[^%.]+") do
    table.insert(jwt_parts, part)
end
if #jwt_parts ~= 3 then
    return
end
local b64 = require "ngx.base64"
local payload_b64 = jwt_parts[2]
local payload_json_str = b64.decode_base64url(payload_b64)
ngx.req.set_header("jwt-user", payload_json_str)
local jwt_user_sign = jwt_parts[3]
ngx.req.set_header("jwt-user-sign", string.sub(jwt_user_sign, 1, 3) .. "..." .. #jwt_user_sign)
