package com.boxbuilder.workplanner.generic.kvstore

abstract class KVStore {

    // ── Registry ──────────────────────────────────────────────

    private val registry = mutableMapOf<String, EntityRegistration<*>>()

    open fun <T : Any> registerEntity(entityName: String, registration: EntityRegistration<T>) {
        require(entityName.isNotBlank()) { "Entity name cannot be blank" }
        require(registration.primaryKey.componentNames.isNotEmpty()) {
            "Primary key must have at least one component"
        }
        registration.indexes.forEach { index ->
            require(index.componentNames.isNotEmpty()) {
                "Index '${index.indexName}' must have at least one component"
            }
        }
        registry[entityName] = registration
    }

    // ── Protected helpers for subclasses ──────────────────────

    protected fun <T : Any> getRegistration(entityName: String): EntityRegistration<T> {
        @Suppress("UNCHECKED_CAST")
        return registry[entityName] as? EntityRegistration<T>
            ?: throw IllegalStateException("Entity '$entityName' not registered")
    }

    protected fun <T : Any> extractPrimaryKey(entityName: String, value: T): Map<String, String> {
        val reg = getRegistration<T>(entityName)
        val extracted = reg.primaryKey.extractor(value)
        validateKeys(
            reg.primaryKey.componentNames, extracted.keys, "PrimaryKey of '$entityName'"
        )
        return extracted
    }

    protected fun <T : Any> extractIndexValues(
        entityName: String, indexName: String, value: T
    ): Map<String, String> {
        val index = findIndex<T>(entityName, indexName)
        val extracted = index.extractor(value)
        validateKeys(
            index.componentNames, extracted.keys, "Index '$indexName' on '$entityName'"
        )
        return extracted
    }

    protected fun validateQueryKeys(
        entityName: String, indexName: String, queryKeys: Set<String>
    ) {
        val index = findIndex<Any>(entityName, indexName)
        validateKeys(index.componentNames, queryKeys, "Query on index '$indexName'")
    }

    protected fun <T : Any> deriveStorageKey(entityName: String, value: T): String {
        val reg = getRegistration<T>(entityName)
        val pkMap = extractPrimaryKey(entityName, value)
        return reg.primaryKey.componentNames.joinToString("#") { pkMap[it]!! }
    }

    // ── Private helpers ───────────────────────────────────────

    private fun <T : Any> findIndex(entityName: String, indexName: String): IndexConfig<T> {
        val reg = getRegistration<T>(entityName)
        return reg.indexes.find { it.indexName == indexName }
            ?: throw IllegalStateException("Index '$indexName' not found on entity '$entityName'")
    }

    private fun validateKeys(expected: List<String>, actual: Set<String>, context: String) {
        val expectedSet = expected.toSet()
        if (actual != expectedSet) {
            throw IllegalStateException(
                "$context: expected keys $expectedSet but extractor returned $actual"
            )
        }
    }

    // ── Abstract methods (implemented by each backend) ────────

    abstract suspend fun <T : Any> save(entity: String, value: T)
    abstract suspend fun <T : Any> saveAll(entity: String, values: List<T>)
    abstract suspend fun <T : Any> get(entity: String, id: String): T?
    abstract suspend fun <T : Any> getAll(entity: String): List<T>
    abstract suspend fun <T : Any> getByIndex(
        entity: String,
        indexName: String,
        indexValues: Map<String, String>
    ): List<T>
    abstract suspend fun delete(entity: String, id: String)
    abstract suspend fun deleteAll(entity: String)
    abstract suspend fun exists(entity: String): Boolean
}
