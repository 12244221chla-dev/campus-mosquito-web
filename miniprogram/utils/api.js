const BASE_URL='https://campus-mosquito-demo.onrender.com';
let cookies=wx.getStorageSync('campus-session')||{};
let csrf='',boot;
function receive(result){
 const header=result.header||{};
 let values=result.cookies||header['Set-Cookie']||header['set-cookie']||[];
 if(typeof values==='string')values=values.split(/,(?=\s*[^;,=]+=[^;]*)/);
 values.forEach(value=>{const pair=value.split(';')[0];const i=pair.indexOf('=');if(i>0){const name=pair.slice(0,i).trim();const val=pair.slice(i+1);if(val)cookies[name]=val;else delete cookies[name];}});
 wx.setStorageSync('campus-session',cookies);
 if(result.data&&result.data.csrfToken)csrf=result.data.csrfToken;
}
function header(){return {'Content-Type':'application/json','Cookie':Object.keys(cookies).map(key=>`${key}=${cookies[key]}`).join('; '),'X-CSRFToken':csrf};}
function raw(path,method='GET',data){return new Promise((resolve,reject)=>wx.request({url:BASE_URL+path,method,data,header:header(),timeout:60000,success(result){receive(result);if(result.statusCode>=200&&result.statusCode<300)resolve(result.data);else reject(new Error(result.data.message||'请求失败'));},fail(){reject(new Error('未连接服务器：请检查开发者工具网络及服务器合法域名配置'));}}));}
function init(){if(!boot)boot=raw('/api/mini/session/').catch(error=>{boot=null;throw error;});return boot;}
async function request(path,method='GET',data){if(method!=='GET')await init();return raw(path,method,data);}
async function upload(path,filePath,data){await init();return new Promise((resolve,reject)=>wx.uploadFile({url:BASE_URL+path,filePath,name:'photo',formData:data,header:{Cookie:header().Cookie,'X-CSRFToken':csrf},timeout:60000,success(result){try{result.data=JSON.parse(result.data);receive(result);if(result.statusCode>=200&&result.statusCode<300)resolve(result.data);else reject(new Error(result.data.message||'上传失败'));}catch(error){reject(error);}},fail(){reject(new Error('图片上传未成功，请检查网络和 uploadFile 合法域名'));}}));}
module.exports={request,upload,BASE_URL};
