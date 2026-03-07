package com.boxbuilder.workplanner.generic.kvstore

import kotlinx.serialization.KSerializer

data class PrimaryKeyConfig<T>(
    val componentNames: List<String>,
    val extractor: (T) -> Map<String, String>
)

data class IndexConfig<T>(
    val indexName: String,
    val componentNames: List<String>,
    val extractor: (T) -> Map<String, String>
)

data class EntityRegistration<T>(
    val primaryKey: PrimaryKeyConfig<T>,
    val indexes: List<IndexConfig<T>>,
    val serializer: KSerializer<T>? = null
)
