from collections.abc import Mapping, Sequence
from pathlib import Path

type JsonScalar = str | int | float | bool | None
type JsonArray = Sequence[JsonValue]
type JsonObject = Mapping[str, JsonValue]
type JsonValue = JsonScalar | JsonArray | JsonObject
type JsonDict = dict[str, JsonValue]
type ConfigScalar = JsonScalar | Path
type ConfigArray = Sequence[ConfigValue]
type ConfigObject = Mapping[str, ConfigValue]
type ConfigValue = ConfigScalar | ConfigArray | ConfigObject
type ConfigData = dict[str, ConfigValue]
type InitSubclassKwargs = ConfigValue
type ResultScalar = JsonScalar | Path
type ResultArray = Sequence[ResultValue]
type ResultObject = Mapping[str, ResultValue]
type ResultValue = ResultScalar | ResultArray | ResultObject
type ResultMetadata = Mapping[str, ResultValue]
type ResultDict = dict[str, ResultValue]
