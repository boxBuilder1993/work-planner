package com.boxbuilder.workplanner.data.model

enum class CommentType { COMMENT, PROPOSAL }

enum class ProposalStatus { PENDING, APPROVED, DENIED }

data class Comment(
    val id: String,
    val taskId: String,
    val text: String,
    val parentCommentId: String? = null,
    val commentType: CommentType = CommentType.COMMENT,
    val createdBy: String = "user",
    val proposalStatus: ProposalStatus? = null,
    val proposalFeedback: String? = null,
    val createdAt: Long,
    val updatedAt: Long
) {
    val isProposal: Boolean get() = commentType == CommentType.PROPOSAL
    val isAgentComment: Boolean get() = createdBy != "user"
    val isThreadReply: Boolean get() = parentCommentId != null
}
