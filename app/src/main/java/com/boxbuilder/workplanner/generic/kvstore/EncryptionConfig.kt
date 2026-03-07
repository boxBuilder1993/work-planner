package com.boxbuilder.workplanner.generic.kvstore

data class EncryptionConfig(
    val key: ByteArray,
    val algorithm: String = "AES/GCM/NoPadding",
    val ivLengthBytes: Int = 12,
    val tagLengthBits: Int = 128
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is EncryptionConfig) return false
        return key.contentEquals(other.key) &&
                algorithm == other.algorithm &&
                ivLengthBytes == other.ivLengthBytes &&
                tagLengthBits == other.tagLengthBits
    }

    override fun hashCode(): Int {
        var result = key.contentHashCode()
        result = 31 * result + algorithm.hashCode()
        result = 31 * result + ivLengthBytes
        result = 31 * result + tagLengthBits
        return result
    }
}
