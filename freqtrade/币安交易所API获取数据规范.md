# 币安交易所API获取数据规范



# 一、币安交易所Websocket行情推送

## 1、连续合约K线

## 数据流描述

K线stream逐秒推送所请求的K线种类(最新一根K线)的更新。

**合约类型:**

- perpetual 永续合约
- current_quarter 当季交割合约
- next_quarter 次季交割合约
- tradifi_perpetual 传统金融合约

**订阅Kline需要提供间隔参数,最短为分钟线,最长为月线。支持以下间隔:**

s -> 秒; m -> 分钟; h -> 小时; d -> 天; w -> 周; M -> 月

- 1s
- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 2h
- 4h
- 6h
- 8h
- 12h
- 1d
- 3d
- 1w
- 1M

## Stream Name

```
<pair>_<contractType>@continuousKline_<interval>
```

## 更新速度

**250ms**

## 响应示例

```javascript
{
  "e":"continuous_kline",	// 事件类型
  "E":1607443058651,		// 事件时间
  "ps":"BTCUSDT",			// 标的交易对
  "ct":"PERPETUAL",			// 合约类型 
  "k":{
    "t":1607443020000,		// 这根K线的起始时间
    "T":1607443079999,		// 这根K线的结束时间
    "i":"1m",				// K线间隔
    "f":116467658886,		// 这根K线期间第一笔更新ID
    "L":116468012423,		// 这根K线期间末一笔更新ID
    "o":"18787.00",			// 这根K线期间第一笔成交价
    "c":"18804.04",			// 这根K线期间末一笔成交价
    "h":"18804.04",			// 这根K线期间最高成交价
    "l":"18786.54",			// 这根K线期间最低成交价
    "v":"197.664",			// 这根K线期间成交量
    "n":543,				// 这根K线期间成交笔数
    "x":false,				// 这根K线是否完结(是否已经开始下一根K线)
    "q":"3715253.19494",	// 这根K线期间成交额
    "V":"184.769",			// 主动买入的成交量
    "Q":"3472925.84746",	// 主动买入的成交额
    "B":"0"					// 忽略此参数
  }
}
```



## 2、K线

## Stream Description

K线stream逐秒推送所请求的K线种类(最新一根K线)的更新。推送间隔250毫秒(如有刷新)

**订阅 Kline 需要提供间隔参数，最短为分钟线，最长为月线。支持以下间隔:**

m -> 分钟; h -> 小时; d -> 天; w -> 周; M -> 月

- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 2h
- 4h
- 6h
- 8h
- 12h
- 1d
- 3d
- 1w
- 1M

## Stream Name

```
<symbol>@kline_<interval>
```

## Update Speed

**250ms**

## Response Example

```javascript
{
  "e": "kline",     // 事件类型
  "E": 123456789,   // 事件时间
  "s": "BNBUSDT",    // 交易对
  "k": {
    "t": 123400000, // 这根K线的起始时间
    "T": 123460000, // 这根K线的结束时间
    "s": "BNBUSDT",  // 交易对
    "i": "1m",      // K线间隔
    "f": 100,       // 这根K线期间第一笔成交ID
    "L": 200,       // 这根K线期间末一笔成交ID
    "o": "0.0010",  // 这根K线期间第一笔成交价
    "c": "0.0020",  // 这根K线期间末一笔成交价
    "h": "0.0025",  // 这根K线期间最高成交价
    "l": "0.0015",  // 这根K线期间最低成交价
    "v": "1000",    // 这根K线期间成交量
    "n": 100,       // 这根K线期间成交笔数
    "x": false,     // 这根K线是否完结(是否已经开始下一根K线)
    "q": "1.0000",  // 这根K线期间成交额
    "V": "500",     // 主动买入的成交量
    "Q": "0.500",   // 主动买入的成交额
    "B": "123456"   // 忽略此参数
  }
}
```



# 二、币安交易所REST API数据

## 1、K线数据

## 接口描述

每根K线的开盘时间可视为唯一ID

## HTTP请求

GET `/fapi/v1/klines`

## 请求权重

取决于请求中的LIMIT参数

| LIMIT参数   | 权重 |
| ----------- | ---- |
| [1,100)     | 1    |
| [100, 500)  | 2    |
| [500, 1000] | 5    |
| > 1000      | 10   |

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                    |
| --------- | ------ | -------- | ----------------------- |
| symbol    | STRING | YES      | 交易对                  |
| interval  | ENUM   | YES      | 时间间隔                |
| startTime | LONG   | NO       | 起始时间                |
| endTime   | LONG   | NO       | 结束时间                |
| limit     | INT    | NO       | 默认值:500 最大值:1500. |

> - 缺省返回最近的数据

## 响应示例

```javascript
[
  [
    1499040000000,      // 开盘时间
    "0.01634790",       // 开盘价
    "0.80000000",       // 最高价
    "0.01575800",       // 最低价
    "0.01577100",       // 收盘价(当前K线未结束的即为最新价)
    "148976.11427815",  // 成交量
    1499644799999,      // 收盘时间
    "2434.19055334",    // 成交额
    308,                // 成交笔数
    "1756.87402397",    // 主动买入成交量
    "28.46694368",      // 主动买入成交额
    "17928899.62484339" // 请忽略该参数
  ]
]
```



## 2、连续合约K线数据

## 接口描述

每根K线的开盘时间可视为唯一ID

## HTTP请求

GET `/fapi/v1/continuousKlines`

## 请求权重

取决于请求中的LIMIT参数

| LIMIT参数   | 权重 |
| ----------- | ---- |
| [1,100)     | 1    |
| [100, 500)  | 2    |
| [500, 1000] | 5    |
| > 1000      | 10   |

## 请求参数

| 名称         | 类型   | 是否必需 | 描述                   |
| ------------ | ------ | -------- | ---------------------- |
| pair         | STRING | YES      | 标的交易对             |
| contractType | ENUM   | YES      | 合约类型               |
| interval     | ENUM   | YES      | 时间间隔               |
| startTime    | LONG   | NO       | 起始时间               |
| endTime      | LONG   | NO       | 结束时间               |
| limit        | INT    | NO       | 默认值:500 最大值:1500 |

- 缺省返回最近的数据
- 合约类型:
  - PERPETUAL 永续合约
  - CURRENT_QUARTER 当季交割合约
  - NEXT_QUARTER 次季交割合约
  - TRADIFI_PERPETUAL 传统金融合约

## 响应示例

```javascript
[
  [
    1607444700000,    	// 开盘时间
    "18879.99",       	// 开盘价
    "18900.00",       	// 最高价
    "18878.98",       	// 最低价
    "18896.13",       	// 收盘价(当前K线未结束的即为最新价)
    "492.363",  		// 成交量
    1607444759999,   	// 收盘时间
    "9302145.66080",    // 成交额
    1874,               // 成交笔数
    "385.983",    		// 主动买入成交量
    "7292402.33267",    // 主动买入成交额
    "0" 				// 请忽略该参数
  ]
]
```



## 3、查询资金费率历史

## 接口描述

查询资金费率历史

## HTTP请求

GET `/fapi/v1/fundingRate`

## 请求权重

和GET /fapi/v1/fundingInfo共享500/5min/IP

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                   |
| --------- | ------ | -------- | ---------------------- |
| symbol    | STRING | NO       | 交易对                 |
| startTime | LONG   | NO       | 起始时间               |
| endTime   | LONG   | NO       | 结束时间               |
| limit     | INT    | NO       | 默认值:100 最大值:1000 |

> - 如果 `startTime` 和 `endTime` 都未发送, 返回最近200条数据.
> - 如果 `startTime` 和 `endTime` 之间的数据量大于 `limit`, 返回 `startTime` + `limit`情况下的数据。

## 响应示例

```javascript
[
	{
    	"symbol": "BTCUSDT",			// 交易对
    	"fundingRate": "-0.03750000",	// 资金费率
    	"fundingTime": 1570608000000,	// 资金费时间
        "markPrice": "34287.54619963"   // 资金费对应标记价格
	},
	{
   		"symbol": "BTCUSDT",
    	"fundingRate": "0.00010000",
    	"fundingTime": 1570636800000,
        "markPrice": "34287.54619963"   // 资金费对应标记价格
	}
]
```



## 4、查询资金费率信息

## 接口描述

查询资金费率信息，接口仅返回FundingRateCap/FundingRateFloor/fundingIntervalHours等被特殊调整过的交易对，没调整过的不返回。

## HTTP请求

GET `/fapi/v1/fundingInfo`

## 请求权重

**0**

和`GET /fapi/v1/fundingRate`共享500/5min/IP

## 请求参数

## 响应示例

```javascript
[
    {
        "symbol": "BLZUSDT",
        "adjustedFundingRateCap": "0.02500000",
        "adjustedFundingRateFloor": "-0.02500000",
        "fundingIntervalHours": 8,
        "disclaimer": false
    }
]
```



## 5、获取未平仓合约数

## 接口描述

获取未平仓合约数

## HTTP请求

GET `/fapi/v1/openInterest`

## 请求权重

**1**

## 请求参数

| 名称   | 类型   | 是否必需 | 描述   |
| ------ | ------ | -------- | ------ |
| symbol | STRING | YES      | 交易对 |

## 响应示例

```javascript
{
	"openInterest": "10659.509", // 未平仓合约数量
	"symbol": "BTCUSDT",	// 交易对
	"time": 1589437530011   // 撮合引擎时间
}
```



## 6、合约持仓量历史

## 接口描述

查询合约持仓量历史

## HTTP请求

GET `/futures/data/openInterestHist`

## 请求权重

**0**

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                                            |
| --------- | ------ | -------- | ----------------------------------------------- |
| symbol    | STRING | YES      |                                                 |
| period    | ENUM   | YES      | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit     | LONG   | NO       | default 30, max 500                             |
| startTime | LONG   | NO       |                                                 |
| endTime   | LONG   | NO       |                                                 |

> - 若无 startime 和 endtime 限制， 则默认返回当前时间往前的limit值
> - 仅支持最近1个月的数据
> - IP限频为1000次/5min

## 响应示例

```javascript
[
    { 
         "symbol":"BTCUSDT",
	      "sumOpenInterest":"20403.12345678",// 持仓总数量
	      "sumOpenInterestValue": "176196512.12345678", // 持仓总价值
          "CMCCirculatingSupply": "165880.538", // CMC提供的流通供应量
	      "timestamp":"1583127900000"
    
     },
     {
     
         "symbol":"BTCUSDT",
         "sumOpenInterest":"20401.36700000",
         "sumOpenInterestValue":"149940752.14464448",
         "CMCCirculatingSupply": "165900.14853",
         "timestamp":"1583128200000"
     },   
]
```



## 7、大户持仓量多空比

## 接口描述

大户的多头和空头总持仓量占比，大户指保证金余额排名前20%的用户。 多仓持仓量比例 = 大户多仓持仓量 / 大户总持仓量 空仓持仓量比例 = 大户空仓持仓量 / 大户总持仓量 多空持仓量比值 = 多仓持仓量比例 / 空仓持仓量比例

## HTTP请求

GET `/futures/data/topLongShortPositionRatio`

## 请求权重

**0**

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                                            |
| --------- | ------ | -------- | ----------------------------------------------- |
| symbol    | STRING | YES      |                                                 |
| period    | ENUM   | YES      | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit     | LONG   | NO       | default 30, max 500                             |
| startTime | LONG   | NO       |                                                 |
| endTime   | LONG   | NO       |                                                 |

> - 若无 startime 和 endtime 限制， 则默认返回当前时间往前的limit值
> - 仅支持最近30天的数据
> - IP限频为1000次/5min

## 响应示例

```javascript
[
    { 
         "symbol":"BTCUSDT",
	      "longShortRatio":"1.4342",// 大户多空持仓量比值
	      "longAccount": "0.5344", // 大户多仓持仓量比例
	      "shortAccount":"0.4238", // 大户空仓持仓量比例
	      "timestamp":"1583139600000"
    
     },
     
     {
         
         "symbol":"BTCUSDT",
	      "longShortRatio":"1.4337",
	      "longAccount": "0.5891", 
	      "shortAccount":"0.4108", 	                
	      "timestamp":"1583139900000"
	               
        },   
	    
]
```



## 8、大户账户数多空比

## 接口描述

持仓大户的净持仓多头和空头账户数占比，大户指保证金余额排名前20%的用户。一个账户记一次。 多仓账户数比例 = 持多仓大户数 / 总持仓大户数 空仓账户数比例 = 持空仓大户数 / 总持仓大户数 多空账户数比值 = 多仓账户数比例 / 空仓账户数比例

## HTTP请求

GET `/futures/data/topLongShortAccountRatio`

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                                            |
| --------- | ------ | -------- | ----------------------------------------------- |
| symbol    | STRING | YES      |                                                 |
| period    | ENUM   | YES      | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit     | LONG   | NO       | default 30, max 500                             |
| startTime | LONG   | NO       |                                                 |
| endTime   | LONG   | NO       |                                                 |

> - 若无 startime 和 endtime 限制， 则默认返回当前时间往前的limit值
> - 仅支持最近30天的数据
> - IP限频为1000次/5min

## 响应示例

```javascript
[
    { 
         "symbol":"BTCUSDT",
	      "longShortRatio":"1.8105",// 大户多空账户数比值
	      "longAccount": "0.6442", // 大户多仓账户数比例
	      "shortAccount":"0.3558", // 大户空仓账户数比例
	      "timestamp":"1583139600000"
    },
    {
         
         "symbol":"BTCUSDT",
	      "longShortRatio":"1.8233",
	      "longAccount": "0.5338", 
	      "shortAccount":"0.3454", 	                
	      "timestamp":"1583139900000"
	}
]
```



## 9、多空持仓人数比

## 接口描述

多空持仓人数比

## HTTP请求

GET `/futures/data/globalLongShortAccountRatio`

## 请求权重

**0**

## 请求参数

| 名称      | 类型   | 是否必需 | 描述                                            |
| --------- | ------ | -------- | ----------------------------------------------- |
| symbol    | STRING | YES      |                                                 |
| period    | ENUM   | YES      | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit     | LONG   | NO       | default 30, max 500                             |
| startTime | LONG   | NO       |                                                 |
| endTime   | LONG   | NO       |                                                 |

> - 若无 startime 和 endtime 限制， 则默认返回当前时间往前的limit值
> - 仅支持最近30天的数据
> - IP限频为1000次/5min

## 响应示例

```javascript
[
    { 
         "symbol":"BTCUSDT",
	      "longShortRatio":"0.1960", // 多空人数比值
	      "longAccount": "0.6622", // 多仓人数比例
	      "shortAccount":"0.3378", // 空仓人数比例
	      "timestamp":"1583139600000"
    
     },
     
     {
         
         "symbol":"BTCUSDT",
	      "longShortRatio":"1.9559",
	      "longAccount": "0.6617", 
	      "shortAccount":"0.3382", 	                
	      "timestamp":"1583139900000"
	               
        },   
	    
]
```



## 10、基差

## 接口描述

查询期货基差

## HTTP请求

GET `/futures/data/basis`

## 请求权重

**0**

## 请求参数

| 名称         | 类型   | 是否必需 | 描述                                            |
| ------------ | ------ | -------- | ----------------------------------------------- |
| pair         | STRING | YES      | BTCUSDT                                         |
| contractType | ENUM   | YES      | CURRENT_QUARTER, NEXT_QUARTER, PERPETUAL        |
| period       | ENUM   | YES      | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit        | LONG   | YES      | Default 30,Max 500                              |
| startTime    | LONG   | NO       |                                                 |
| endTime      | LONG   | NO       |                                                 |

> - 若无 startime 和 endtime 限制， 则默认返回当前时间往前的limit值
> - 仅支持最近30天的数据

## 响应示例

```javascript
[  
    {
        "indexPrice": "34400.15945055",
        "contractType": "PERPETUAL",
        "basisRate": "0.0004",
        "futuresPrice": "34414.10",
        "annualizedBasisRate": "",
        "basis": "13.94054945",
        "pair": "BTCUSDT",
        "timestamp": 1698742800000
    }
]
```



## 11、24hr价格变动情况

## 接口描述

请注意，不携带symbol参数会返回全部交易对数据，不仅数据庞大，而且权重极高

## HTTP请求

GET `/fapi/v1/ticker/24hr`

## 请求权重

带symbol为**1**, 不带为**40**

## 请求参数

| 名称   | 类型   | 是否必需 | 描述   |
| ------ | ------ | -------- | ------ |
| symbol | STRING | NO       | 交易对 |

> - 不发送交易对参数，则会返回所有交易对信息

## 响应示例

```javascript
{
  "symbol": "BTCUSDT",
  "priceChange": "-94.99999800",    //24小时价格变动
  "priceChangePercent": "-95.960",  //24小时价格变动百分比
  "weightedAvgPrice": "0.29628482", //加权平均价
  "lastPrice": "4.00000200",        //最近一次成交价
  "lastQty": "200.00000000",        //最近一次成交额
  "openPrice": "99.00000000",       //24小时内第一次成交的价格
  "highPrice": "100.00000000",      //24小时最高价
  "lowPrice": "0.10000000",         //24小时最低价
  "volume": "8913.30000000",        //24小时成交量
  "quoteVolume": "15.30000000",     //24小时成交额
  "openTime": 1499783499040,        //24小时内，第一笔交易的发生时间
  "closeTime": 1499869899040,       //24小时内，最后一笔交易的发生时间
  "firstId": 28385,   // 首笔成交id
  "lastId": 28460,    // 末笔成交id
  "count": 76         // 成交笔数
}
```



> 或(当不发送交易对信息)

```javascript
[
	{
  		"symbol": "BTCUSDT",
  		"priceChange": "-94.99999800",    //24小时价格变动
  		"priceChangePercent": "-95.960",  //24小时价格变动百分比
  		"weightedAvgPrice": "0.29628482", //加权平均价
  		"lastPrice": "4.00000200",        //最近一次成交价
  		"lastQty": "200.00000000",        //最近一次成交额
  		"openPrice": "99.00000000",       //24小时内第一次成交的价格
  		"highPrice": "100.00000000",      //24小时最高价
  		"lowPrice": "0.10000000",         //24小时最低价
  		"volume": "8913.30000000",        //24小时成交量
  		"quoteVolume": "15.30000000",     //24小时成交额
  		"openTime": 1499783499040,        //24小时内，第一笔交易的发生时间
  		"closeTime": 1499869899040,       //24小时内，最后一笔交易的发生时间
  		"firstId": 28385,   // 首笔成交id
  		"lastId": 28460,    // 末笔成交id
  		"count": 76         // 成交笔数
    }
]
```